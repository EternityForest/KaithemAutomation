

try:
    from django.forms.models import model_to_dict
    from django.db.models import Model
except ImportError:
    model_to_dict = None


def safe_model_to_dict(model):
    if model_to_dict is None:
        return model
    if isinstance(model, Model):
        return model_to_dict(model)
    return model
