class PaymentError(Exception):
    status_code: int


class CartNotFoundError(PaymentError):
    status_code = 404


class CartNotActiveError(PaymentError):
    status_code = 409


class CartEmptyError(PaymentError):
    status_code = 422


class PaymentMethodIdNotFoundError(PaymentError):
    status_code = 404


class PaymentMethodNotOwnedError(PaymentError):
    status_code = 403


class NoDefaultPaymentMethodError(PaymentError):
    status_code = 422


class PaymentAlreadyExistsError(PaymentError):
    status_code = 409
