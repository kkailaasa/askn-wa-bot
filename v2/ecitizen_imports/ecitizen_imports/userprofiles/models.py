from django.db import models
from django.contrib.auth.models import User
from simple_history.models import HistoricalRecords
from django.core.validators import MinValueValidator, MaxValueValidator

from cities_light.models import Country, Region, City
from project.models import CommonFieldsModel
from zones.models import UserZone
from .fields import HexadecimalMonthField, GenderField, EPassportStatusField, IntentionField

class UserProfile(models.Model):
    
    first_name = models.CharField(max_length=100, blank=False, null=True)
    last_name = models.CharField(max_length=100, blank=False, null=True)
    spiritual_name = models.CharField(max_length=200, blank=False, null=True)    
    
    date_of_birth = models.DateField(blank=False, null=True)
    gender = GenderField()
    intention = IntentionField(blank=False, null=True, default=None)
    
    phone_number = models.CharField(max_length=20, blank=False, null=True)
    phone_number_verified = models.BooleanField(blank=False, null=False, default=False)
    email = models.EmailField(blank=False, null=False)
    zone = models.ForeignKey(UserZone, null=True, on_delete=models.CASCADE)
    
    country = models.ForeignKey(Country, null=True, on_delete=models.CASCADE)
    state = models.ForeignKey(Region, null=True, on_delete=models.CASCADE)
    city = models.ForeignKey(City, null=True, on_delete=models.CASCADE)
    address_1 = models.CharField(max_length=150, blank=False, null=False)
    postal_code = models.CharField(max_length=20,blank=False, null=False)

    
    user = models.OneToOneField(User, blank=False, null=False, unique=True, on_delete=models.CASCADE)
    
    under_18 = models.BooleanField(blank=False, null=True)
    
    history = HistoricalRecords()
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.id}, {self.email}, {self.gender}"
    
    class Meta:
        indexes = [
            models.Index(fields=['updated_at']),  # Add index to updated_at field
        ]

class UserProfilePhoto(CommonFieldsModel):
    user_profile = models.OneToOneField(UserProfile, on_delete=models.CASCADE)
    photo_base64 = models.TextField(blank=True, null=True)
    nationality = models.CharField(max_length=100, blank=False, null=True)
    
    
class EPassportUserProfile(models.Model):    
    epassport_number = models.CharField(max_length=20, blank=False, null=True, unique=True)
    
    status = EPassportStatusField(null=True)
    month = HexadecimalMonthField(null=True)
    year = models.IntegerField(null=True,
        validators=[
            MinValueValidator(00, message='Minimum value should be 00.'),
            MaxValueValidator(99, message='Maximum value should be 99.'),
        ]
    )
    
    gender = GenderField(null=True)
    
    zone =  models.ForeignKey(UserZone, null=True, on_delete=models.SET_NULL)
    
    country_iso = models.CharField(max_length=2, blank=False, null=True)
    
    number = models.IntegerField(null=True,
        validators=[
            MinValueValidator(10000, message='Minimum value should be 10000.'),
            MaxValueValidator(99999, message='Maximum value should be 99999.'),
        ]
    )
    
    user_profile = models.OneToOneField(UserProfile, blank=False, null=True, on_delete=models.SET_NULL)
    
    history = HistoricalRecords()
    
    class Meta:
        unique_together = ('zone', 'month', 'year', 'number')

class EPassportNumber(CommonFieldsModel):    
    epassport_number = models.CharField(max_length=10, blank=False, null=False, unique=True)
    
    alphabet = models.CharField(max_length=1, blank=False, null=False)
    number = models.IntegerField(null=False, blank=False,
        validators=[
            MinValueValidator(100000000, message='Minimum value should be 100000000.'),
            MaxValueValidator(999999999, message='Maximum value should be 999999999.'),
        ]
    )
    
    user_profile = models.OneToOneField(UserProfile, blank=False, null=False, on_delete=models.DO_NOTHING)
    
    history = HistoricalRecords()
    
    class Meta:
        unique_together = ('alphabet', 'number')


# Register the model with auditlog
from auditlog.registry import auditlog
auditlog.register(UserProfile)
