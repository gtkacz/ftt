import inspect
from collections.abc import Callable
from typing import Any

from django.db.models import Model
from django.forms.models import model_to_dict


def get_default_args(func: Callable) -> dict[str, Any]:
	"""
	This function returns a dictionary with the default arguments of a function.

	Args:
	    func (Callable): The function to get the default arguments from.

	Returns:
	    Dict[str, Any]: The default arguments of the function.

	Example:
	    >>> def foo(a, b=1, c=2):
	    ...     pass
	    >>> get_default_args(foo)
	    {'b': 1, 'c': 2}
	"""
	signature = inspect.signature(func)
	return {k: v.default for k, v in signature.parameters.items() if v.default is not inspect.Parameter.empty}


def django_obj_to_dict(object: type[Model], *, exclude_fields: list[str] = list()) -> dict[str, Any]:
	"""
	This function converts a Django model object to a dictionary.

	Args:
	    object (Type[Model]): The Django model object to convert.

	Returns:
	    Dict[str, Any]: The dictionary representation of the Django model object.
	"""
	return model_to_dict(
		object,
		fields=[field.name for field in object._meta.fields if field.name not in exclude_fields],
	)


def get_number_suffix(number: float) -> str:
	"""
	Get the ordinal suffix for a given number.

	Args:
	    number: The number to get the suffix for.

	Returns:
	    str: The ordinal suffix ('st', 'nd', 'rd', 'th') for the number.
	"""
	if 10 <= number % 100 <= 20:
		return "th"

	return {1: "st", 2: "nd", 3: "rd"}.get(int(number) % 10, "th")
