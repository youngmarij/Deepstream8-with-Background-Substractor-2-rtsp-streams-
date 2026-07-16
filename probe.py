import gi
gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst
from pathlib import Path
import cv2
import config
import pyds
import ctypes
import cupy as cp
import datetime
import numpy as np
from parser import parse_args
args = parse_args()


frame_cnt = 0
bg_subtractor = cv2.createBackgroundSubtractorMOG2(
    history=500,
    varThreshold=36,
    detectShadows=False
)

def on_new_sample(appsink, user_data):
    sample = appsink.emit("pull-sample")
    if not sample:
        print("ERROR: Failed to pull sample")
        return Gst.FlowReturn.ERROR
    
    gst_buffer = sample.get_buffer()
    if not gst_buffer:
        print("ERROR: Failed to get buffer")
        return Gst.FlowReturn.ERROR
            
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    if not batch_meta:
        print("ERROR: No batch meta found")
        return Gst.FlowReturn.ERROR
    
    l_frame = batch_meta.frame_meta_list
    frames_processed = 0
    
    while l_frame is not None:
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break
        
        frame_index = frame_meta.batch_id
        global frame_cnt
        frame_cnt += 1
        

        data_type, shape, strides, dataptr, size = pyds.get_nvds_buf_surface_gpu(
            hash(gst_buffer), frame_index
        )
        
        if not dataptr:
            print(f"ERROR: Failed to get surface for frame {frame_index}")
            l_frame = l_frame.next
            continue

        ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
        ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
        c_data_ptr = ctypes.pythonapi.PyCapsule_GetPointer(dataptr, None)
        unownedmem = cp.cuda.UnownedMemory(c_data_ptr, size, owner=None) 
        memptr = cp.cuda.MemoryPointer(unownedmem, 0)

        n_frame_gpu = cp.ndarray(
            shape=shape, 
            dtype=data_type, 
            memptr=memptr, 
            strides=strides, 
            order='C'
        )
        n_frame_cpu = cp.asnumpy(n_frame_gpu)
        
        fg_mask = bg_subtractor.apply(n_frame_cpu)

        kernel = np.ones((5, 5), np.uint8)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        frame_with_boxes = cv2.cvtColor(fg_mask, cv2.COLOR_GRAY2BGR)

        min_area = 500
        objects_count = 0
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > min_area:
                x, y, w, h = cv2.boundingRect(contour)
                cv2.rectangle(frame_with_boxes, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(frame_with_boxes, f'Obj {int(area)}', 
                           (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 
                           0.5, (0, 255, 0), 2)
                objects_count += 1

        cv2.putText(frame_with_boxes, f'Frame: {frame_cnt}', 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(frame_with_boxes, f'Objects: {objects_count}', 
                   (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        
        if args.rtsp_ts:
            ts = frame_meta.ntp_timestamp / 1000000000
            time_str = datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            cv2.putText(frame_with_boxes, f'Time: {time_str}', 
                       (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        frame_bytes = frame_with_boxes.tobytes()
   

        new_buffer = Gst.Buffer.new_allocate(None, len(frame_bytes), None)
        if not new_buffer:
            print("ERROR: Failed to allocate new buffer")
            l_frame = l_frame.next
            continue
        
        new_buffer.fill(0, frame_bytes)
        new_buffer.pts = gst_buffer.pts
        new_buffer.dts = gst_buffer.dts
        new_buffer.duration = gst_buffer.duration
        

        appsrc = user_data
        
        
        ret = appsrc.emit("push-buffer", new_buffer)
        
        if ret != Gst.FlowReturn.OK:
            print(f"ERROR: Failed to push buffer: {ret}")
            return Gst.FlowReturn.ERROR
        
        frames_processed += 1
        
        try:
            l_frame = l_frame.next
        except StopIteration:
            break
    
    if frames_processed == 0:
        return Gst.FlowReturn.ERROR
    return Gst.FlowReturn.OK

def pgie_src_pad_buffer_probe(pad, info, u_data):
    
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return Gst.PadProbeReturn.OK

    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    
    while l_frame is not None:
        # frame_cnt += 1
        
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break
        
        frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        
        frame_number = frame_meta.frame_num
        print(f"Frame Number={frame_number}")

        try:
            l_frame = l_frame.next
        except StopIteration:
            break

    return Gst.PadProbeReturn.OK
