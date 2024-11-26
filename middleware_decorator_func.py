from functools import wraps
from typing import Callable, Any

class ValidationDecorator:
    """Middleware decorator class"""
    
    @staticmethod
    def pre_validate(validation_func: Callable) -> Callable:
        def decorator(method: Callable) -> Callable:
            @wraps(method)
            def wrapper(instance: Any, *args, **kwargs) -> Any:
                validation_func(instance, *args, **kwargs)
                return method(instance, *args, **kwargs)
            return wrapper
        return decorator

    @staticmethod
    def post_validate(validation_func: Callable) -> Callable:
        def decorator(method: Callable) -> Callable:
            @wraps(method)
            def wrapper(instance: Any, *args, **kwargs) -> Any:
                # Execute method first
                result = method(instance, *args, **kwargs)
                # Then run validation
                validation_func(instance, result, *args, **kwargs)
                return result
            return wrapper
        return decorator

class BankAccount:
    """Bank account class"""
    
    def __init__(self, balance: float = 0.0):
        self.balance = balance
        
    def _validate_positive_amount(self, amount: float, *args, **kwargs) -> None:
        if amount <= 0:
            raise ValueError("Amount must be positive")
            
    def _validate_sufficient_balance(self, amount: float, *args, **kwargs) -> None:
        if self.balance < amount:
            raise ValueError("Insufficient balance")
            
    def _validate_balance_not_exceeded(self, result: float, *args, **kwargs) -> None:
        if result > 1000000:
            raise ValueError("Balance cannot exceed 1,000,000")

    @ValidationDecorator.pre_validate(_validate_positive_amount)
    @ValidationDecorator.pre_validate(_validate_sufficient_balance)
    def withdraw(self, amount: float) -> float:
        self.balance -= amount
        return self.balance

    @ValidationDecorator.pre_validate(_validate_positive_amount)
    @ValidationDecorator.post_validate(_validate_balance_not_exceeded)
    def deposit(self, amount: float) -> float:
        self.balance += amount
        return self.balance
    


if __name__ == '__main__':
    account = BankAccount(100.0)

    account.deposit(50.0)  # Works fine
    account.withdraw(30.0)  # Works fine

    # # Invalid operations that will raise exceptions
    try:
        account.deposit(-50.0)  # Raises ValueError: Amount must be positive
    except ValueError as e:
        print(e)

    try:
        account.withdraw(200.0)  # Raises ValueError: Insufficient balance
    except ValueError as e:
        print(e)

    try:
        account.deposit(2000000.0)  # Raises ValueError: Balance cannot exceed 1,000,000
    except ValueError as e:
        print(e)