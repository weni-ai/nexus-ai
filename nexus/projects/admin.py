from django.contrib import admin
from nexus.projects.models import Project

class ProjectAdmin(admin.ModelAdmin):
    raw_id_fields = ["org", "created_by"]

admin.site.register(Project, ProjectAdmin)