class AlphaSDKException(Exception):
    """Lỗi chung của SDK"""
    pass

class GatewayTimeout(AlphaSDKException):
    """Lỗi khi Gateway không phản hồi kịp thời"""
    pass

class GatewayReject(AlphaSDKException):
    """Lỗi khi Gateway chủ động từ chối lệnh (400, 403, 429)"""
    pass