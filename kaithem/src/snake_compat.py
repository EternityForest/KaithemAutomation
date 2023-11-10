# https://stackoverflow.com/a/44969381/2360612

def camel_to_kebab(s):
    return ''.join(['_' + c.lower() if c.isupper() else c for c in s]).lstrip('_')


def kebab_to_snake(s):
    return s.replace('-', '_')


def snake_to_kebab(s):
    return s.replace('-', '_')


def snake_to_camel(s):
    temp = s.split('_')
    return temp[0] + ''.join(ele.title() for ele in temp[1:])
     

def camel_to_snake(s):
    return ''.join(['_' + c.lower() if c.isupper() else c for c in s]).lstrip('_')


def snakify_dict(d):
    return {camel_to_snake(kebab_to_snake(i)): d[i] for i in d}


def kebab_dict(d):
    return {snake_to_kebab(camel_to_kebab(i)): d[i] for i in d}


def camel_dict(d):
    return {snake_to_camel(kebab_to_snake(i)): d[i] for i in d}
