class BusinessError(Exception):
    def __init__(
        self,
        code: str = "B000001",
        message: str = "系统执行出错",
        *,
        http_status: int = 200,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
