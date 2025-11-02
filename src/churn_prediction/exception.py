import sys
import traceback
from typing import Optional, Tuple
from src.churn_prediction.logger import logger


def format_error_message(
    error: Exception,
    error_detail: sys,
    include_traceback: bool = True
) -> str:
    """
    Format detailed error message with file name, line number, and error context.
    
    Args:
        error (Exception): The exception that was raised
        error_detail (sys): The sys module for accessing exception info
        include_traceback (bool): Whether to include full traceback
    
    Returns:
        str: Formatted error message with details
    
    Example:
        >>> try:
        >>>     1 / 0
        >>> except ZeroDivisionError as e:
        >>>     msg = format_error_message(e, sys)
    """
    try:
        _, _, exc_tb = error_detail.exc_info()
        
        if exc_tb is None:
            return str(error)
        
        file_name = exc_tb.tb_frame.f_code.co_filename
        line_number = exc_tb.tb_lineno
        function_name = exc_tb.tb_frame.f_code.co_name
        error_text = str(error)
        
        detailed_message = (
            f"Error in file '{file_name}' | "
            f"Function '{function_name}' | "
            f"Line {line_number} | "
            f"Error: {error_text}"
        )
        
        if include_traceback:
            tb_str = traceback.format_exc()
            detailed_message += f"\n\nTraceback:\n{tb_str}"
        
        return detailed_message
    except Exception as e:
        logger.error(f"Error formatting error message: {str(e)}")
        return str(error)


class CustomException(Exception):
    """
    Custom exception class for application-specific errors.
    
    Provides detailed error information including file name, line number,
    function name, and optional full traceback.
    
    Example:
        >>> try:
        >>>     some_operation()
        >>> except Exception as e:
        >>>     raise CustomException(f"Operation failed: {str(e)}", sys) from e
    """
    
    def __init__(
        self,
        error_message: str,
        error_detail: sys,
        include_traceback: bool = True
    ):
        """
        Initialize CustomException with detailed error information.
        
        Args:
            error_message (str): The main error message
            error_detail (sys): The sys module for exception details
            include_traceback (bool): Include full traceback in error message
        """
        super().__init__(error_message)
        self.error_message = error_message
        self.detailed_message = format_error_message(
            Exception(error_message),
            error_detail,
            include_traceback=include_traceback
        )
        
        # Log the error for monitoring
        logger.error(self.detailed_message)
    
    def __str__(self) -> str:
        """Return the detailed error message."""
        return self.detailed_message
    
    def __repr__(self) -> str:
        """Return the representation of the exception."""
        return f"{self.__class__.__name__}({self.error_message})"