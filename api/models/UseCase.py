from django.db import models
from django.utils.text import slugify

from api.utls.enums import UseCaseStatus
from api.utls.file_paths import _use_case_directory_path


class UseCase(models.Model):
    title = models.CharField(max_length=200, unique=True)
    description = models.CharField(max_length=1000)
    logo = models.ImageField(upload_to=_use_case_directory_path, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    website = models.URLField(blank=True)
    contact_email = models.EmailField(blank=True, null=True)
    slug = models.SlugField(max_length=75, null=True, blank=False, unique=True)
    status = models.CharField(max_length=50, default=UseCaseStatus.DRAFT, choices=UseCaseStatus.choices)
    datasets = models.ManyToManyField('Dataset', blank=True)

    def save(self, *args, **kwargs):
        self.slug = slugify(self.title)
        super().save(*args, **kwargs)
