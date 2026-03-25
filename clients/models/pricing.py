from django.db import models
from django.utils.translation import gettext_lazy as _
from .payment import Payment

class ServicePrice(models.Model):
    service_code = models.CharField(
        max_length=50,
        unique=True,
        choices=Payment.SERVICE_CHOICES,
        verbose_name=_("Код услуги")
    )
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00,
        verbose_name=_("Цена (PLN)")
    )
    
    class Meta:
        verbose_name = _("Цена на услугу")
        verbose_name_plural = _("Цены на услуги")
        
    def __str__(self):
        return f"{self.get_service_code_display()}: {self.price} PLN"
