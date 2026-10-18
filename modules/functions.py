import itertools

def MergeLists(value: list) -> list:
	"""
	Раскрывает вложенные списки внутри списка-контейнера.

	Раскрытие происходит при выполнении условий:
	1. Список-контейнер не пуст.
	2. Первый элемент списка-контейнера является списком.

	:param value: Список-контейнер, который может содержать списки.
	:type value: list
	:return: Обработанный список.
	:rtype: list
	"""
	
	if len(value) > 0 and type(value[0]) is list:
		return list(itertools.chain.from_iterable(value))

	return value