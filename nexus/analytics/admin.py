from django.contrib import admin
from django.urls import path
from django.http import HttpResponse
from rest_framework.test import APIRequestFactory, force_authenticate
import json

from nexus.analytics.api.views import (
    ResolutionRateAverageView,
    ResolutionRateIndividualView,
    UnresolvedRateView,
    ProjectsByMotorView,
)
from nexus.projects.models import Project


def get_analytics_action(view_class, action_name, description):
    """Factory function to create admin actions for analytics endpoints"""

    def analytics_action(modeladmin, request, queryset):
        factory = APIRequestFactory()
        view = view_class.as_view()
        results = []

        for project in queryset:
            # Build query params based on view type
            query_params = {}
            
            if view_class == ResolutionRateAverageView:
                query_params["project_uuid"] = str(project.uuid)
                url_path = "/api/analytics/resolution-rate/average/"
            elif view_class == UnresolvedRateView:
                query_params["project_uuid"] = str(project.uuid)
                url_path = "/api/analytics/unresolved-rate/"
            elif view_class == ResolutionRateIndividualView:
                query_params["filter_project_uuid"] = str(project.uuid)
                url_path = "/api/analytics/resolution-rate/individual/"
            elif view_class == ProjectsByMotorView:
                query_params = {"motor": "both"}  # Projects by Motor doesn't filter by project
                url_path = "/api/analytics/projects/by-motor/"
            else:
                continue
            
            if request.GET.get("start_date"):
                query_params["start_date"] = request.GET["start_date"]
            if request.GET.get("end_date"):
                query_params["end_date"] = request.GET["end_date"]
            if request.GET.get("motor"):
                query_params["motor"] = request.GET["motor"]
            if request.GET.get("min_conversations"):
                query_params["min_conversations"] = request.GET["min_conversations"]

            # Create Django request (APIRequestFactory returns HttpRequest)
            django_request = factory.get(url_path, query_params)
            
            # Force authentication for DRF - this ensures IsAuthenticated permission passes
            force_authenticate(django_request, user=request.user)

            # Call view - DRF will automatically wrap HttpRequest in Request
            response = view(django_request)

            if hasattr(response, "data"):
                results.append(
                    {
                        "project": project.name,
                        "project_uuid": str(project.uuid),
                        "status_code": response.status_code,
                        "data": response.data,
                    }
                )
            else:
                results.append(
                    {
                        "project": project.name,
                        "project_uuid": str(project.uuid),
                        "status_code": response.status_code,
                        "error": "No data in response",
                    }
                )

        # Format results for display
        message_parts = []
        for result in results:
            if result["status_code"] == 200:
                data_str = json.dumps(result["data"], indent=2)
                message_parts.append(
                    f"\n\n{result['project']} ({result['project_uuid'][:8]}...):\n{data_str}"
                )
            else:
                error_data = result.get("error", result.get("data", {}))
                message_parts.append(
                    f"\n\n{result['project']} ({result['project_uuid'][:8]}...): "
                    f"Error {result['status_code']} - {error_data}"
                )

        from django.contrib import messages
        messages.success(
            request,
            f"{description} Results:{''.join(message_parts)}",
        )

    analytics_action.short_description = description
    analytics_action.__name__ = action_name
    return analytics_action


# Create specific actions for all analytics endpoints
get_average_resolution_rate = get_analytics_action(
    ResolutionRateAverageView, "get_average_resolution_rate", "Get Average Resolution Rate"
)

get_unresolved_rate = get_analytics_action(
    UnresolvedRateView, "get_unresolved_rate", "Get Unresolved Rate"
)

get_individual_resolution_rate = get_analytics_action(
    ResolutionRateIndividualView, "get_individual_resolution_rate", "Get Individual Resolution Rate"
)

get_projects_by_motor = get_analytics_action(
    ProjectsByMotorView, "get_projects_by_motor", "Get Projects by Motor"
)


# Custom admin views for global endpoints
def average_resolution_rate_view(request):
    """Admin view for Average Resolution Rate endpoint"""
    factory = APIRequestFactory()
    view = ResolutionRateAverageView.as_view()
    response_data = None
    status_code = None
    query_params = {}

    if request.method == "POST":
        # Get query params from form
        start_date = request.POST.get("start_date", "").strip()
        end_date = request.POST.get("end_date", "").strip()
        motor = request.POST.get("motor", "").strip()
        min_conversations = request.POST.get("min_conversations", "").strip()
        project_uuid = request.POST.get("project_uuid", "").strip()

        query_params = {
            "start_date": start_date,
            "end_date": end_date,
            "motor": motor,
            "min_conversations": min_conversations,
            "project_uuid": project_uuid,
        }
        # Remove empty params
        query_params = {k: v for k, v in query_params.items() if v}

        django_request = factory.get("/api/analytics/resolution-rate/average/", query_params)
        force_authenticate(django_request, user=request.user)

        response = view(django_request)
        response_data = response.data if hasattr(response, "data") else {}
        status_code = response.status_code

    # Build simple HTML response
    html = f"""
    <html>
        <head><title>Average Resolution Rate Analytics</title></head>
        <body>
            <h1>Average Resolution Rate Analytics</h1>
            <form method="post">
                <p>Project UUID (optional): <input type="text" name="project_uuid" value="{query_params.get('project_uuid', '')}" placeholder="Leave empty for all projects"></p>
                <p>Start Date (YYYY-MM-DD): <input type="date" name="start_date" value="{query_params.get('start_date', '')}"></p>
                <p>End Date (YYYY-MM-DD): <input type="date" name="end_date" value="{query_params.get('end_date', '')}"></p>
                <p>Motor: 
                    <select name="motor">
                        <option value="">All</option>
                        <option value="AB 2" {'selected' if query_params.get('motor') == 'AB 2' else ''}>AB 2</option>
                        <option value="AB 2.5" {'selected' if query_params.get('motor') == 'AB 2.5' else ''}>AB 2.5</option>
                    </select>
                </p>
                <p>Min Conversations: <input type="number" name="min_conversations" value="{query_params.get('min_conversations', '')}"></p>
                <p><button type="submit">Run Query</button></p>
            </form>
            {f'<h2>Results (Status: {status_code})</h2><pre>{json.dumps(response_data, indent=2)}</pre>' if response_data else ''}
        </body>
    </html>
    """
    return HttpResponse(html)


def unresolved_rate_view(request):
    """Admin view for Unresolved Rate endpoint"""
    factory = APIRequestFactory()
    view = UnresolvedRateView.as_view()
    response_data = None
    status_code = None
    query_params = {}

    if request.method == "POST":
        # Get query params from form
        start_date = request.POST.get("start_date", "").strip()
        end_date = request.POST.get("end_date", "").strip()
        motor = request.POST.get("motor", "").strip()
        min_conversations = request.POST.get("min_conversations", "").strip()
        project_uuid = request.POST.get("project_uuid", "").strip()

        query_params = {
            "start_date": start_date,
            "end_date": end_date,
            "motor": motor,
            "min_conversations": min_conversations,
            "project_uuid": project_uuid,
        }
        # Remove empty params
        query_params = {k: v for k, v in query_params.items() if v}

        django_request = factory.get("/api/analytics/unresolved-rate/", query_params)
        force_authenticate(django_request, user=request.user)

        response = view(django_request)
        response_data = response.data if hasattr(response, "data") else {}
        status_code = response.status_code

    # Build simple HTML response
    html = f"""
    <html>
        <head><title>Unresolved Rate Analytics</title></head>
        <body>
            <h1>Unresolved Rate Analytics</h1>
            <form method="post">
                <p>Project UUID (optional): <input type="text" name="project_uuid" value="{query_params.get('project_uuid', '')}" placeholder="Leave empty for all projects"></p>
                <p>Start Date (YYYY-MM-DD): <input type="date" name="start_date" value="{query_params.get('start_date', '')}"></p>
                <p>End Date (YYYY-MM-DD): <input type="date" name="end_date" value="{query_params.get('end_date', '')}"></p>
                <p>Motor: 
                    <select name="motor">
                        <option value="">All</option>
                        <option value="AB 2" {'selected' if query_params.get('motor') == 'AB 2' else ''}>AB 2</option>
                        <option value="AB 2.5" {'selected' if query_params.get('motor') == 'AB 2.5' else ''}>AB 2.5</option>
                    </select>
                </p>
                <p>Min Conversations: <input type="number" name="min_conversations" value="{query_params.get('min_conversations', '')}"></p>
                <p><button type="submit">Run Query</button></p>
            </form>
            {f'<h2>Results (Status: {status_code})</h2><pre>{json.dumps(response_data, indent=2)}</pre>' if response_data else ''}
        </body>
    </html>
    """
    return HttpResponse(html)


def individual_resolution_rate_view(request):
    """Admin view for Individual Resolution Rate endpoint"""
    factory = APIRequestFactory()
    view = ResolutionRateIndividualView.as_view()
    response_data = None
    status_code = None
    query_params = {}

    if request.method == "POST":
            # Get query params from form
            start_date = request.POST.get("start_date", "").strip()
            end_date = request.POST.get("end_date", "").strip()
            motor = request.POST.get("motor", "").strip()
            min_conversations = request.POST.get("min_conversations", "").strip()
            filter_project_uuid = request.POST.get("filter_project_uuid", "").strip()
            filter_project_name = request.POST.get("filter_project_name", "").strip()

            query_params = {
                "start_date": start_date,
                "end_date": end_date,
                "motor": motor,
                "min_conversations": min_conversations,
                "filter_project_uuid": filter_project_uuid,
                "filter_project_name": filter_project_name,
            }
            # Remove empty params
            query_params = {k: v for k, v in query_params.items() if v}

            django_request = factory.get("/api/analytics/resolution-rate/individual/", query_params)
            force_authenticate(django_request, user=request.user)

            response = view(django_request)
            response_data = response.data if hasattr(response, "data") else {}
            status_code = response.status_code

    # Build simple HTML response
    html = f"""
    <html>
        <head><title>Individual Resolution Rate Analytics</title></head>
        <body>
            <h1>Individual Resolution Rate Analytics</h1>
            <form method="post">
                <p>Start Date (YYYY-MM-DD): <input type="date" name="start_date" value="{query_params.get('start_date', '')}"></p>
                <p>End Date (YYYY-MM-DD): <input type="date" name="end_date" value="{query_params.get('end_date', '')}"></p>
                <p>Motor: 
                    <select name="motor">
                        <option value="">All</option>
                        <option value="AB 2" {'selected' if query_params.get('motor') == 'AB 2' else ''}>AB 2</option>
                        <option value="AB 2.5" {'selected' if query_params.get('motor') == 'AB 2.5' else ''}>AB 2.5</option>
                    </select>
                </p>
                <p>Min Conversations: <input type="number" name="min_conversations" value="{query_params.get('min_conversations', '')}"></p>
                <p>Filter Project UUID: <input type="text" name="filter_project_uuid" value="{query_params.get('filter_project_uuid', '')}"></p>
                <p>Filter Project Name: <input type="text" name="filter_project_name" value="{query_params.get('filter_project_name', '')}"></p>
                <p><button type="submit">Run Query</button></p>
            </form>
            {f'<h2>Results (Status: {status_code})</h2><pre>{json.dumps(response_data, indent=2)}</pre>' if response_data else ''}
        </body>
        </html>
    """
    return HttpResponse(html)


def projects_by_motor_view(request):
    """Admin view for Projects by Motor endpoint"""
    factory = APIRequestFactory()
    view = ProjectsByMotorView.as_view()
    response_data = None
    status_code = None
    query_params = {}

    if request.method == "POST":
        motor = request.POST.get("motor", "both")
        start_date = request.POST.get("start_date", "").strip()
        end_date = request.POST.get("end_date", "").strip()

        query_params = {"motor": motor}
        if start_date and end_date:
            query_params["start_date"] = start_date
            query_params["end_date"] = end_date

        django_request = factory.get("/api/analytics/projects/by-motor/", query_params)
        force_authenticate(django_request, user=request.user)

        response = view(django_request)
        response_data = response.data if hasattr(response, "data") else {}
        status_code = response.status_code

    # Build simple HTML response
    html = f"""
    <html>
    <head><title>Projects by Motor Analytics</title></head>
        <body>
            <h1>Projects by Motor Analytics</h1>
            <form method="post">
                <p>Motor: 
                    <select name="motor">
                        <option value="both" {'selected' if query_params.get('motor', 'both') == 'both' else ''}>Both</option>
                        <option value="AB 2" {'selected' if query_params.get('motor') == 'AB 2' else ''}>AB 2</option>
                        <option value="AB 2.5" {'selected' if query_params.get('motor') == 'AB 2.5' else ''}>AB 2.5</option>
                    </select>
                </p>
                <p>Start Date (YYYY-MM-DD): <input type="date" name="start_date" value="{query_params.get('start_date', '')}"></p>
                <p>End Date (YYYY-MM-DD): <input type="date" name="end_date" value="{query_params.get('end_date', '')}"></p>
                <p><button type="submit">Run Query</button></p>
            </form>
            {f'<h2>Results (Status: {status_code})</h2><pre>{json.dumps(response_data, indent=2)}</pre>' if response_data else ''}
        </body>
    </html>
    """
    return HttpResponse(html)


# Create a dashboard page with buttons/links to analytics endpoints
def analytics_dashboard(request):
    """Main analytics dashboard with buttons to access all endpoints"""
    html = f"""
    <html>
    <head>
        <title>Analytics Dashboard</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; }}
            .dashboard {{ max-width: 1200px; margin: 0 auto; }}
            .card {{ background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px; padding: 20px; margin: 20px 0; }}
            .card h2 {{ margin-top: 0; color: #495057; }}
            .button {{ 
                display: inline-block; 
                padding: 12px 24px; 
                background: #007bff; 
                color: white; 
                text-decoration: none; 
                border-radius: 4px; 
                margin: 5px;
                border: none;
                cursor: pointer;
            }}
            .button:hover {{ background: #0056b3; }}
            .button-secondary {{ background: #6c757d; }}
            .button-secondary:hover {{ background: #545b62; }}
            .description {{ color: #6c757d; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="dashboard">
            <h1>📊 Analytics Resolution Endpoints</h1>
            
            <div class="card">
                <h2>All Analytics Endpoints</h2>
                <p class="description">All endpoints are now global-scoped. Use optional filters to narrow down scraped projects.</p>
                
                <div style="margin-top: 15px;">
                    <a href="/admin/analytics/average-resolution-rate/" class="button">
                        📊 Average Resolution Rate
                    </a>
                    <p style="margin-left: 5px; color: #6c757d; font-size: 14px;">
                        Get aggregated resolution rate metrics (optionally filter by project)
                    </p>
                </div>
                
                <div style="margin-top: 15px;">
                    <a href="/admin/analytics/unresolved-rate/" class="button">
                        ⚠️ Unresolved Rate
                    </a>
                    <p style="margin-left: 5px; color: #6c757d; font-size: 14px;">
                        Get unresolved conversation rate metrics (optionally filter by project)
                    </p>
                </div>
                
                <div style="margin-top: 15px;">
                    <a href="/admin/analytics/individual-resolution-rate/" class="button">
                        📈 Individual Resolution Rate
                    </a>
                    <p style="margin-left: 5px; color: #6c757d; font-size: 14px;">
                        Get resolution rate metrics broken down by individual projects
                    </p>
                </div>
                
                <div style="margin-top: 15px;">
                    <a href="/admin/analytics/projects-by-motor/" class="button">
                        🚀 Projects by Motor
                    </a>
                    <p style="margin-left: 5px; color: #6c757d; font-size: 14px;">
                        Get list of projects grouped by motor type (AB 2 or AB 2.5)
                    </p>
                </div>
            </div>
            
            <div class="card">
                <h2>Quick Links</h2>
                <a href="/admin/" class="button button-secondary">← Back to Admin</a>
                <a href="/admin/projects/project/" class="button button-secondary">View Projects</a>
            </div>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html)


# Apply mixin to admin site by patching get_urls method
_original_get_urls = admin.site.get_urls


def get_urls_with_analytics():
    """Wrapper to add analytics URLs to admin"""
    urls = _original_get_urls()
    custom_urls = [
        # Main dashboard with buttons/links
        path(
            "analytics/",
            admin.site.admin_view(analytics_dashboard),
            name="analytics_dashboard",
        ),
        # All endpoint views
        path(
            "analytics/average-resolution-rate/",
            admin.site.admin_view(average_resolution_rate_view),
            name="analytics_average_resolution_rate",
        ),
        path(
            "analytics/unresolved-rate/",
            admin.site.admin_view(unresolved_rate_view),
            name="analytics_unresolved_rate",
        ),
        path(
            "analytics/individual-resolution-rate/",
            admin.site.admin_view(individual_resolution_rate_view),
            name="analytics_individual_resolution_rate",
        ),
        path(
            "analytics/projects-by-motor/",
            admin.site.admin_view(projects_by_motor_view),
            name="analytics_projects_by_motor",
        ),
    ]
    return custom_urls + urls


admin.site.get_urls = get_urls_with_analytics
