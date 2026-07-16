import gi
gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import GstRtspServer

def start_rtsp_servers(codec, rtsp_port_num, updsink_port_num, rtsp_port_num_2, updsink_port_num_2):

    server = GstRtspServer.RTSPServer.new()
    server.props.service = "%d" % rtsp_port_num
    server.attach(None)

    factory = GstRtspServer.RTSPMediaFactory.new()
    factory.set_launch(
        '( udpsrc name=pay0 port=%d buffer-size=524288 caps="application/x-rtp, media=video, clock-rate=90000, encoding-name=(string)%s, payload=96 " )'
        % (updsink_port_num, codec)
    )
    factory.set_shared(True)
    server.get_mount_points().add_factory("/ds-test", factory)

    print(
        "\n *** DeepStream: Launched RTSP Streaming at rtsp://localhost:%d/ds-test ***\n\n"
        % rtsp_port_num
    )

    server_2 = GstRtspServer.RTSPServer.new()
    server_2.props.service = "%d" % rtsp_port_num_2
    server_2.attach(None)

    factory_2 = GstRtspServer.RTSPMediaFactory.new()
    factory_2.set_launch(
        '( udpsrc name=pay0 port=%d buffer-size=524288 caps="application/x-rtp, media=video, clock-rate=90000, encoding-name=(string)%s, payload=96 " )'
        % (updsink_port_num_2, codec)
    )
    factory_2.set_shared(True)
    server_2.get_mount_points().add_factory("/bg-test", factory_2)

    print(
        "\n *** DeepStream: Launched RTSP Streaming at rtsp://localhost:%d/bg-test ***\n\n"
        % rtsp_port_num_2
    )
