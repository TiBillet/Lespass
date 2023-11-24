from django import template

register = template.Library()

@register.filter
def modulo(num, val):
    return num % val

@register.filter
def range_by(events: list, val: int):
    list_ranged = []
    iteration = 0
    count_list = -1
    for event in events:
        if iteration % val == 0:
            count_list += 1
            list_ranged.append([event,])
        else :
            list_ranged[count_list].append(event)
        iteration += 1

    return list_ranged

@register.filter
def in_list(value, list):
    value = str(value)
    retour = value in list.split(',')
    return retour

@register.filter
def not_in_list(value, list):
    value = str(value)
    retour = value not in list.split(',')
    return retour

@register.filter
def price_can_be_displayed(adhesion_obligatoire, is_login):
    print(f"adhesion_obligatoire = {adhesion_obligatoire}")
    print(f"is_login = {is_login}")
    if adhesion_obligatoire == None:
        return True

    return False