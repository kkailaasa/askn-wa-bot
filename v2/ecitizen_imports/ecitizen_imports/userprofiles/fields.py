from django.db import models
from django.core.validators import RegexValidator

class HexadecimalMonthField(models.IntegerField):
    HEXADECIMAL_REGEX = r'^[1-9A-C]$'
    HEXADECIMAL_VALIDATOR = RegexValidator(
        regex=HEXADECIMAL_REGEX,
        message='Enter a valid hexadecimal month value (1 to C).',
        code='invalid_hexadecimal_month'
    )

    def __init__(self, *args, **kwargs):
        kwargs['validators'] = [self.HEXADECIMAL_VALIDATOR]
        kwargs['choices'] = [(i, hex(i)[2:].upper()) for i in range(1, 13)]
        #kwargs['default'] = 1
        super().__init__(*args, **kwargs)

class GenderField(models.CharField):
    GENDER_CHOICES = (
        ('M', 'Male'),
        ('F', 'Female'),
        #('O', 'Other'),
    )
    
    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = 1
        kwargs['choices'] = self.GENDER_CHOICES
        super().__init__(*args, **kwargs)

class IntentionField(models.CharField):
    CHOICES = (
        ('N', 'None'),
        ('S', 'Sanyas/Monk'),
        ('G', 'Grihastha'),
    )
    
    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = 1
        kwargs['choices'] = self.CHOICES
        super().__init__(*args, **kwargs)

                
class EPassportStatusField(models.CharField):
    STATUS_CHOICES = (
        ('V', 'Verified'),
        ('T', 'Temporary'),
        ('F', 'Free'),
    )
    
    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = 1
        kwargs['choices'] = self.STATUS_CHOICES
        super().__init__(*args, **kwargs)