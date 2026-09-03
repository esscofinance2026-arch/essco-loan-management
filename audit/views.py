# audit/views.py
from django.shortcuts import render, redirect
import logging
from django.contrib.auth import authenticate, login, logout
from django.core.paginator import Paginator  # ← Add this
from django.db.models import Q  # ← Add this
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import cache_control, never_cache
from accounts.decorators import unauthenticated_user, allowed_users
from . import models as Essco_Models
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model
from datetime import datetime, timedelta
from django.utils import timezone

# Get the custom User model
User = get_user_model()

Essco_allowed_roles=['admin', 'manager', 'officer']


@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='login')
@allowed_users(allowed_roles=Essco_allowed_roles)
def logs(request):
    """Display audit logs with filtering, sorting, and pagination."""
    logs = Essco_Models.AuditLog.objects.select_related('user', 'application', 'loan').all()

    # Filtering
    action = request.GET.get('action')
    if action:
        logs = logs.filter(action=action)

    user_id = request.GET.get('user')
    if user_id:
        logs = logs.filter(user_id=user_id)

    search = request.GET.get('search')
    if search:
        logs = logs.filter(
            Q(description__icontains=search) |
            Q(ip_address__icontains=search) |
            Q(user__username__icontains=search) |
            Q(user__email__icontains=search) |
            Q(loan__loan_id__icontains=search)
        )

    # Date filtering
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if date_from:
        try:
            # Parse date from string (assuming format YYYY-MM-DD)
            date_from_parsed = datetime.strptime(date_from, '%Y-%m-%d')
            # Make it timezone aware if using timezone
            date_from_aware = timezone.make_aware(date_from_parsed) if timezone.is_naive(date_from_parsed) else date_from_parsed
            logs = logs.filter(created__gte=date_from_aware)
        except ValueError:
            pass  # Invalid date format, ignore filter

    if date_to:
        try:
            # Parse date from string (assuming format YYYY-MM-DD)
            date_to_parsed = datetime.strptime(date_to, '%Y-%m-%d')
            # Add one day to include the entire day
            date_to_parsed = date_to_parsed + timedelta(days=1)
            # Make it timezone aware if using timezone
            date_to_aware = timezone.make_aware(date_to_parsed) if timezone.is_naive(date_to_parsed) else date_to_parsed
            logs = logs.filter(created__lte=date_to_aware)
        except ValueError:
            pass  # Invalid date format, ignore filter

    # Pre-defined date range filters
    date_range = request.GET.get('date_range')
    if date_range:
        now = timezone.now()
        if date_range == 'today':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            logs = logs.filter(created__gte=start)
        elif date_range == 'yesterday':
            yesterday = now - timedelta(days=1)
            start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
            logs = logs.filter(created__range=[start, end])
        elif date_range == 'week':
            start = now - timedelta(days=7)
            logs = logs.filter(created__gte=start)
        elif date_range == 'month':
            start = now - timedelta(days=30)
            logs = logs.filter(created__gte=start)
        elif date_range == 'last_month':
            # First day of last month to last day of last month
            first_day_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            last_day_last_month = first_day_this_month - timedelta(days=1)
            first_day_last_month = last_day_last_month.replace(day=1)
            logs = logs.filter(created__range=[first_day_last_month, last_day_last_month])

    # Sorting
    sort_by = request.GET.get('sort', '-created')
    if sort_by:
        logs = logs.order_by(sort_by)

    # Pagination
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get users who have audit logs
    users = User.objects.filter(auditlog__isnull=False).distinct()

    context = {
        'audit_logs': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'is_paginated': page_obj.has_other_pages(),
        'action_choices': Essco_Models.AuditLog.ACTIONS,
        'users': users,
        'sort_by': sort_by,
        'sort_dir': 'asc' if sort_by.startswith('') else 'desc',
        # Pass date filters back to template for maintaining state
        'date_from': date_from,
        'date_to': date_to,
        'date_range': date_range,
    }

    return render(request, 'log1.html', context)


@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='login')
@allowed_users(allowed_roles=Essco_allowed_roles)
def logsview(request, pk):
    log = Essco_Models.AuditLog.objects.get(id=pk)
    context = {'log': log,}
    return render(request, 'logview.html', context)


