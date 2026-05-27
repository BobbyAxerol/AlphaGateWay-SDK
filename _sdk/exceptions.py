class AlphaSDKException(Exception):
    """Lỗi chung của SDK"""
    pass

class GatewayError(AlphaSDKException):
    """Lỗi khi Gateway trả về code 4xx hoặc 5xx"""
    def __init__(self, status_code, message):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Gateway Error {status_code}: {message}")

class LockAcquisitionError(AlphaSDKException):
    """Không thể lấy Lock cho Symbol (lệnh trước đang xử lý)"""
    pass

class GatewayTimeout(AlphaSDKException):
    """Gateway không phản hồi trong thời gian quy định"""
    pass

class GatewayReject(AlphaSDKException):
    """Gateway từ chối lệnh"""
    pass

class LockActiveException(AlphaSDKException):
    """Symbol đang bị khóa do có lệnh đang xử lý"""
    pass