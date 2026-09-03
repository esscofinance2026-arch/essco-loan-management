# ===== DJANGO CORE =====
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import cache_control, never_cache
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.db import IntegrityError
from django.db.models import Count, Sum, Avg, Q
from django.core.cache import cache
from django.template.loader import render_to_string
from django.utils.html import escape
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import json
import logging
import traceback
import time
import uuid
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import hashlib
from django.db import transaction
from django.contrib.admin.views.decorators import staff_member_required
from applications.services.email_counter import EmailCounter

# ✅ Import LoanProduct for staff views
from loans.models import LoanProduct
from payments.models import PaymentRecord, PaymentMethod
from loans.services.loan_creation_service import LoanCreationService

# ===== PROJECT APPS =====
from applications import forms as Essco_Forms
from applications import models as Essco_Models
from applications import emails as Essco_Emails
from applications.helpers import (
    get_user_application,
    get_user_applications,
    get_customer_context
)
from applications.permissions import ApplicationPermissions, CustomerPermissions

from accounts.decorators import (
    unauthenticated_user,
    allowed_users,
    customer_required,
    officer_required,
    manager_required,
    admin_required
)
from accounts.models import SiteSettings
from accounts.forms import MaintenanceSettingsForm

from audit.models import AuditLog
from audit.services import (
    log_action,
    AuditService,
    get_client_ip,
    get_geo_location,
    get_location_display
)
from audit.change_tracker import ChangeTracker



# ===== AUTH =====
from django.contrib.auth import authenticate, login, logout, get_user_model



# Get the custom User model
User = get_user_model()
logger = logging.getLogger(__name__)

Essco_allowed_roles=['admin', 'manager', 'officer']

# Create your views here.






def test_timeout(request):
    """Test endpoint to simulate timeout"""
    # Simulate a slow request (25 seconds)
    # This will trigger your timeout handling
    time.sleep(25)
    return JsonResponse({'status': 'success'})

def test_force_timeout(request):
    """Forces a timeout by waiting 60 seconds"""
    time.sleep(60)  # ⏰ 60 seconds (will definitely timeout)
    return JsonResponse({'status': 'success'})







def Finance_Application_Form(request):
    return render(request, 'Finance_Application_Form.html')

def finance(request):
    context = {'is_admin': request.user.is_staff, 'is_superuser': request.user.is_superuser,}
    return render(request, 'finance.html', context)
    #return render(request, 'Appbase.html')



############################################################################################################################################################
##############################################################     Loan Calculator      ####################################################################
############################################################################################################################################################
def loan_calculator(request):
    """Loan calculator page"""
    context = {'title': 'Loan Calculator - ESSCO',}
    return render(request, 'loan_calculator.html', context)

############################################################################################################################################################
#################################################################     About us      #######################################################################
############################################################################################################################################################
def about_us(request):
    context = {'is_admin': request.user.is_staff, 'is_superuser': request.user.is_superuser,}
    return render(request, 'aboutus.html', context)

############################################################################################################################################################
#################################################################     Contact us      #######################################################################
############################################################################################################################################################
def contact_us(request):
    context = {'is_admin': request.user.is_staff, 'is_superuser': request.user.is_superuser,}
    return render(request, 'contactus.html', context)

############################################################################################################################################################
###################################################################     terms      #########################################################################
############################################################################################################################################################
def terms(request):
    context = {'is_admin': request.user.is_staff, 'is_superuser': request.user.is_superuser,}
    return render(request, 'terms.html', context)

############################################################################################################################################################
###################################################################     Privacy      #########################################################################
############################################################################################################################################################
def privacy(request):
    context = {'is_admin': request.user.is_staff, 'is_superuser': request.user.is_superuser,}
    return render(request, 'privacy.html', context)

############################################################################################################################################################
#################################################################     Location      #######################################################################
############################################################################################################################################################
def location(request):
    context = {'is_admin': request.user.is_staff, 'is_superuser': request.user.is_superuser,}
    return render(request, 'store_locator.html', context)


############################################################################################################################################################
#################################################################     Apply      #######################################################################
############################################################################################################################################################

def apply(request):
    # ⭐ Generate or retrieve a unique session ID for this browsing session
    if 'browse_id' not in request.session:
        request.session['browse_id'] = str(uuid.uuid4())

    browse_id = request.session['browse_id']

    # Get product data from URL parameters
    item_name = request.GET.get('item_name', '')
    item_sku = request.GET.get('item_sku', '')
    item_price = request.GET.get('item_price', '')
    item_url = request.GET.get('item_url', '')
    source = request.GET.get('source', '')

    print("The Product SKU is - ",item_sku," The Product name is ",item_name," The Cost is " ,item_price, " This came from ",item_url)

    # ⭐ Store WordPress data in namespaced session (prevents tab collision)
    if item_name and item_sku and item_price:
        # Get existing wp_data or create new
        wp_data = request.session.get('wp_data', {})

        # Store in a nested structure with browse_id as key
        wp_data[browse_id] = {
            'item_name': item_name,
            'item_sku': item_sku,
            'item_price': item_price,
            'item_url': item_url,
            'source': source,
            'timestamp': str(time.time()),
        }
        request.session['wp_data'] = wp_data

    # ⭐ Retrieve from session using browse_id (in case of validation failure)
    wp_data = request.session.get('wp_data', {})
    current_data = wp_data.get(browse_id, {})

    session_item_name = current_data.get('item_name', item_name)
    session_item_sku = current_data.get('item_sku', item_sku)
    session_item_price = current_data.get('item_price', item_price)
    session_item_url = current_data.get('item_url', item_url)
    session_source = current_data.get('source', source)

    # ✅ CLEAN THE PRICE: Remove $ and commas
    cleaned_price = session_item_price
    if cleaned_price:
        # Remove $, commas, and any other non-numeric characters except decimal point
        cleaned_price = cleaned_price.replace('$', '').replace(',', '').strip()
        # Try to convert to float to validate
        try:
            cleaned_price = float(cleaned_price)
        except ValueError:
            cleaned_price = 0.00

    # Initialize form with initial values from WordPress
    initial_data = {
        'item_name': session_item_name,
        'item_sku': session_item_sku,
        'item_price': session_item_price,
    }

    # Only set Purchase_Value if product data exists
    if session_item_name:
        initial_data['Purchase_Value'] = cleaned_price

    if request.method == 'POST':
        # Rate limit: 5 applications per hour per IP
        ip = get_client_ip(request)
        cache_key = f"apply_limit_{ip}"
        attempts = cache.get(cache_key, 0)

        if attempts >= 5:  # 5 attempts per hour
            messages.error(request, "Too many applications from this IP. Please try again later.")
            # Create context for error
            form = Essco_Forms.ApplicationForm(initial=initial_data)
            context = {
                'item_name': escape(session_item_name),
                'item_sku': escape(session_item_sku),
                'item_price': escape(session_item_price),
                'item_url': escape(session_item_url),
                'source': escape(session_source),
                'cleaned_price': cleaned_price,
                'form': form,
                'is_admin': request.user.is_staff if request.user.is_authenticated else False,
                'is_superuser': request.user.is_superuser if request.user.is_authenticated else False,
            }
            return render(request, "loan_application.html", context)

        # ⭐ Increment counter (only on POST)
        cache.set(cache_key, attempts + 1, 3600)  # 1 hour expiry


        # ⭐ Include WordPress data in POST data
        post_data = request.POST.copy()
        if session_item_name:
            post_data['item_name'] = session_item_name
            post_data['item_sku'] = session_item_sku
            post_data['item_price'] = session_item_price

        form = Essco_Forms.ApplicationForm(post_data, request.FILES, initial=initial_data)

        if form.is_valid():
            # =============================================================
            # STEP 1: Get IP and location (with fallback)
            # =============================================================
            ip = get_client_ip(request)

            # Try to get location, but don't fail if it doesn't work
            location = f"IP: {ip}"
            try:
                geo = get_geo_location(ip)
                if geo.get('city') != 'Unknown' and geo.get('country') != 'Unknown':
                    location = f"{geo['city']}, {geo['country']} (IP: {ip})"
            except Exception as e:
                logger.warning(f"Could not get location for {ip}: {e}")

            # =============================================================
            # STEP 2: Save application
            # =============================================================
            application = form.save(commit=False)

            # ✅ Add the WordPress data directly to the model
            if session_item_name:
                # Check if your model has these fields
                if hasattr(application, 'item_name'):
                    application.item_name = session_item_name
                if hasattr(application, 'item_sku'):
                    application.item_sku = session_item_sku
                if hasattr(application, 'item_price'):
                    application.item_price = session_item_price

            if request.user.is_authenticated:
                application.created_by = request.user

            # ✅ DEBUG: Check values before save
            print("=" * 50)
            print("DEBUG: Values BEFORE save")
            print(f"application.item_name: {getattr(application, 'item_name', 'Not Set')}")
            print(f"application.item_sku: {getattr(application, 'item_sku', 'Not Set')}")
            print(f"application.Purchase_Value: {application.Purchase_Value}")
            print("=" * 50)

            try:
                # Gets the current year
                year = timezone.now().year

                # Gets the latest application
                last_application = (
                    Essco_Models.ApplicationModel.objects
                    .filter(reference_number__startswith=f"ESS-{year}-")
                    .order_by('-reference_number')
                    .first()
                )

                if last_application and last_application.reference_number:
                    try:
                        last_number = int(
                            last_application.reference_number.split('-')[-1]
                        )
                    except (ValueError, IndexError):
                        last_number = 0
                else:
                    last_number = 0

                next_number = last_number + 1

                application.reference_number = f"ESS-{year}-{next_number:06d}"

                application.save()

            except IntegrityError as e:
                logger.error(f"Database integrity error: {e}")
                messages.error(request, "A database error occurred. Please try again.")

                context = {
                    'item_name': escape(session_item_name),
                    'item_sku': escape(session_item_sku),
                    'item_price': escape(session_item_price),
                    'item_url': escape(session_item_url),
                    'source': escape(session_source),
                    'cleaned_price': cleaned_price,
                    'form': form,
                    'is_admin': request.user.is_staff if request.user.is_authenticated else False,
                    'is_superuser': request.user.is_superuser if request.user.is_authenticated else False,
                }

                return render(request, 'loan_application.html', context)

            except Exception as e:
                logger.error(f"Database error: {e}")
                messages.error(request, "An error occurred saving your application. Please try again.")

                context = {
                    'item_name': escape(session_item_name),
                    'item_sku': escape(session_item_sku),
                    'item_price': escape(session_item_price),
                    'item_url': escape(session_item_url),
                    'source': escape(session_source),
                    'cleaned_price': cleaned_price,
                    'form': form,
                    'is_admin': request.user.is_staff if request.user.is_authenticated else False,
                    'is_superuser': request.user.is_superuser if request.user.is_authenticated else False,
                }

                return render(request, 'loan_application.html', context)

            # =============================================================
            # ✅ STORE THE APPLICATION ID IN THE SESSION
            # =============================================================
            request.session['last_application_id'] = application.id

            # =============================================================
            # ✅ LOG: the application Creation Right after save)
            # =============================================================
            log_action(request=request, user=request.user if request.user.is_authenticated else "Anonymous",
                action='CREATE',  # ✅ Use 'CREATE' action (must exist in your ACTIONS choices)
                application=application,
                description=(
                    f"Application created for {application.Fname} {application.Lname} "
                    f"(ID: {application.ID_number}) from {location}"
                ),
                ip_address=ip
            )

            # =============================================================
            # STEP 3: Send confirmation email (separate try block)
            # =============================================================
            print("this is the approval status: ",application.Approval_Status)
            email_sent = False
            try:
                # Clean the value first
                status = application.Approval_Status.strip()

                if (status == "Rejected"):
                    Essco_Emails.send_rejection_email(application)
                elif (status == "Approved Pending"):
                    Essco_Emails.send_application_ap_confirmation(application)
                else:
                    Essco_Emails.send_application_confirmation(application)
                email_sent = True

                logger.info(
                    "EMAIL SENT | Application=%s | User=%s",
                    application.id,
                    request.user.username if request.user.is_authenticated else "Anonymous"
                )

            except Exception as e:
                logger.exception(
                    "EMAIL FAILED | Application=%s | User=%s | Error: %s",
                    application.id,
                    request.user.username if request.user.is_authenticated else "Anonymous",
                    str(e)
                )

                messages.warning(
                    request,
                    "⚠️ Application submitted but we couldn't send a confirmation email. "
                    "Our team will contact you shortly."
                )

            # =============================================================
            # STEP 4: Log the action
            # =============================================================
            log_action(
                request=request,
                user=request.user if request.user.is_authenticated else "Anonymous",
                action='EMAIL_SENT' if email_sent else 'EMAIL_FAILED',
                application=application,
                description=(
                    f"{'Confirmation email sent to' if email_sent else 'Confirmation email FAILED for'} "
                    f"{application.email} for {application.Fname} {application.Lname} "
                    f"(ID: {application.ID_number}) from {location}"
                ),
                ip_address=ip
            )

            logger.info(
                "APPLICATION CREATED | ID=%s | User=%s",
                application.id,
                request.user.username if request.user.is_authenticated else "Anonymous"
            )

            # ⭐ Clear ONLY this browse_id from session data
            wp_data = request.session.get('wp_data', {})
            if browse_id in wp_data:
                del wp_data[browse_id]
                request.session['wp_data'] = wp_data

            # ⭐ Clear session data after successful submission
            request.session.pop('wp_item_name', None)
            request.session.pop('wp_item_sku', None)
            request.session.pop('wp_item_price', None)
            request.session.pop('wp_item_url', None)
            request.session.pop('wp_source', None)

            return redirect('Thank_You')

        else:
            # ⭐ Form is invalid - keep the WordPress data from session
            logger.warning(
                "APPLICATION INVALID | User=%s | Errors=%s",
                request.user.username if request.user.is_authenticated else "Anonymous",
                form.errors
            )

            # ⭐ The form already has the data from session, just continue
            # No need to recreate the form

    else:
        # GET request - create form with initial data
        form = Essco_Forms.ApplicationForm(initial=initial_data)

    # ⭐ Use session data for context (not just URL params)
    context = {
        # Product data from WordPress (from session)
        'item_name': escape(session_item_name),
        'item_sku': escape(session_item_sku),
        'item_price': escape(session_item_price),
        'item_url': escape(session_item_url),
        'source': escape(session_source),
        'cleaned_price': cleaned_price,

        'form': form,
        'is_admin': request.user.is_staff if request.user.is_authenticated else False,
        'is_superuser': request.user.is_superuser if request.user.is_authenticated else False,
    }

    return render(request, "loan_application.html", context)

############################################################################################################################################################
##############################################################     Thank You Page      #####################################################################
############################################################################################################################################################

def Thank_You(request):
    """Thank you page with the correct application reference."""

    # =============================================================
    # ✅ GET THE APPLICATION FROM THE SESSION
    # =============================================================
    reference = "ESS-000001"  # Default fallback

    application_id = request.session.get('last_application_id')

    if application_id:
        try:
            application = Essco_Models.ApplicationModel.objects.get(id=application_id)
            reference = application.reference_number
        except Essco_Models.ApplicationModel.DoesNotExist:
            # Application was deleted, use fallback
            reference = "ESS-000001"

    context = {
        'reference': reference,
        'is_admin': request.user.is_staff if request.user.is_authenticated else False,
        'is_superuser': request.user.is_superuser if request.user.is_authenticated else False,
    }
    return render(request, 'Thank_you_for_Application.html', context)

############################################################################################################################################################
#################################################################     DashBoard      #######################################################################
############################################################################################################################################################
@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='login')
@allowed_users(allowed_roles=Essco_allowed_roles)
def admin_dashboard(request):
    # ============================================================
    # GET PARAMETERS
    # ============================================================

    filter_type = request.GET.get('filter', 'all').strip()
    search_query = request.GET.get('search', '').strip()
    page_number = request.GET.get('page', 1)

    # ============================================================
    # BASE QUERYSET
    # ============================================================

    application = (
        Essco_Models.ApplicationModel.objects
        .all()
        .order_by('-created')
    )

    # ============================================================
    # TOTAL APPLICATIONS
    # This remains the total number of applications in the system,
    # regardless of the selected filter/search.
    # ============================================================

    total_applications = (
        Essco_Models.ApplicationModel.objects.count()
    )

    # ============================================================
    # STATUS COUNTS
    # These counts are independent of the current filter/search.
    # ============================================================

    reject_count = (
        Essco_Models.ApplicationModel.objects
        .filter(Approval_Status="Rejected")
        .count()
    )

    AP = (
        Essco_Models.ApplicationModel.objects
        .filter(Approval_Status="Approved Pending")
        .count()
    )

    HR = (
        Essco_Models.ApplicationModel.objects
        .filter(Approval_Status="Human Review")
        .count()
    )

    final_approved_count = (
        Essco_Models.ApplicationModel.objects
        .filter(Final_Approval="Human Approved")
        .count()
    )

    # ============================================================
    # APPLY STATUS FILTER
    # ============================================================

    if filter_type == 'rejected':

        application = application.filter(
            Approval_Status="Rejected"
        )

    elif filter_type == 'human':

        application = application.filter(
            Approval_Status="Human Review"
        )

    elif filter_type == 'approved':

        application = application.filter(
            Approval_Status="Approved Pending"
        )

    elif filter_type == 'final_approved':

        application = application.filter(
            Final_Approval="Human Approved"
        )

    # If filter_type == 'all', no status filter is applied.

    # ============================================================
    # APPLY SEARCH
    #
    # Searches:
    #   - ID Number
    #   - Reference Number
    #   - First Name
    #   - Last Name
    # ============================================================

    if search_query:

        application = application.filter(
            Q(ID_number__icontains=search_query) |
            Q(reference_number__icontains=search_query) |
            Q(Fname__icontains=search_query) |
            Q(Lname__icontains=search_query)
        )

    # ============================================================
    # PAGINATION
    # ============================================================

    paginator = Paginator(application, 10)

    try:
        page_obj = paginator.page(page_number)

    except PageNotAnInteger:
        page_obj = paginator.page(1)

    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # ============================================================
    # CURRENT FILTERED/SEARCHED COUNT
    # ============================================================

    filtered_count = application.count()

    # ============================================================
    # CONTEXT
    # ============================================================

    context = {
        # Applications displayed on this page
        'application': page_obj,

        # Pagination object
        'page_obj': page_obj,

        # Counts
        'total_app': total_applications,
        'filtered_count': filtered_count,

        'reject_count': reject_count,
        'AP': AP,
        'HR': HR,
        'final_approved_count': final_approved_count,

        # Search/filter state
        'current_filter': filter_type,
        'search_query': search_query,

        # User information
        'is_admin': request.user.role == 'admin',
        'is_superuser': request.user.is_superuser,
        'user_role': request.user.role,
    }

    return render(
        request,
        'Application_Dash.html',
        context
    )

###############################################################     DashBoard Edit      #####################################################################


@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='login')
@allowed_users(allowed_roles=Essco_allowed_roles)
def admin_dashboard_edit(request, pk):
    application = Essco_Models.ApplicationModel.objects.get(id=pk)

    # ✅ Store original instance for change tracking
    original_application = Essco_Models.ApplicationModel.objects.get(id=pk)

    form = Essco_Forms.AdminApplicationForm(instance=application)

    if request.method == 'POST':
        # ============================================================
        # ✅ OPTIMISTIC LOCKING CHECK
        # ============================================================
        form_version = int(request.POST.get('version', 0))

        # Check if version matches (fetch fresh from DB)
        current_application = Essco_Models.ApplicationModel.objects.get(id=pk)
        if form_version != current_application.version:
            messages.error(
                request,
                "⚠️ This application has been modified by another user since you opened it. "
                "Please refresh to see the latest changes and re-apply your modifications."
            )
            # Redirect to refresh the form with latest data
            return redirect('admin_dashboard_edit', pk=pk)

        form = Essco_Forms.AdminApplicationForm(request.POST, request.FILES, instance=application)

        if form.is_valid():
            application = form.save(commit=False)
            application.updated_by = request.user

            # ✅ Increment version on successful update
            application.version += 1
            application.save()

            # Get IP and location
            ip = get_client_ip(request)
            location = f"IP: {ip}"
            try:
                geo = get_geo_location(ip)
                if geo.get('city') != 'Unknown' and geo.get('country') != 'Unknown':
                    location = f"{geo['city']}, {geo['country']} (IP: {ip})"
            except Exception as e:
                logger.warning(f"Could not get location for {ip}: {e}")

            # =============================================================
            # Track changes using the ChangeTracker service
            # =============================================================
            description = ChangeTracker.get_change_description(
                original_application,
                application,
                location
            )

            log_action(
                request=request,
                user=request.user if request.user.is_authenticated else "Anonymous",
                action='UPDATE',
                application=application,
                description=description,
                ip_address=ip
            )

            messages.success(request, f"✅ Application {application.reference_number} updated successfully!")

            action = request.POST.get("action")
            if action == "save_continue":
                return redirect("admin_dashboard_edit", pk=application.pk)
            return redirect('admin_dashboard')

        else:
            # Form invalid - show errors
            messages.error(request, "Please correct the errors below.")

    print(form.errors)
    context = {
        'application': application,
        'form': form,
        'is_admin': request.user.is_staff,
        'is_superuser': request.user.is_superuser,
        'version': application.version,  # ✅ Pass version to template
    }
    return render(request, 'Application_Dash_Edit1.html', context)

###############################################################     DashBoard Edit      #####################################################################
@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='login')
@allowed_users(allowed_roles=Essco_allowed_roles)
def admin_dashboard_editold(request, pk):
    application = Essco_Models.ApplicationModel.objects.get(id=pk)

    # ✅ Store original instance for change tracking
    original_application = Essco_Models.ApplicationModel.objects.get(id=pk)

    form = Essco_Forms.AdminApplicationForm(instance=application)

    if request.method == 'POST':
        form = Essco_Forms.AdminApplicationForm(request.POST, request.FILES, instance=application)

        if form.is_valid():
            application = form.save(commit=False)
            application.updated_by = request.user
            application.save()

            # Get IP and location
            ip = get_client_ip(request)
            location = f"IP: {ip}"
            try:
                geo = get_geo_location(ip)
                if geo.get('city') != 'Unknown' and geo.get('country') != 'Unknown':
                    location = f"{geo['city']}, {geo['country']} (IP: {ip})"
            except Exception as e:
                logger.warning(f"Could not get location for {ip}: {e}")

            # =============================================================
            # ✅ ONE LINE - Track changes using the ChangeTracker service
            # =============================================================
            description = ChangeTracker.get_change_description(
                original_application,
                application,
                location
            )

            log_action(
                request=request,
                user=request.user if request.user.is_authenticated else "Anonymous",
                action='UPDATE',
                application=application,
                description=description,
                ip_address=ip
            )

            action = request.POST.get("action")
            if action == "save_continue":
                return redirect("admin_dashboard_edit", pk=application.pk)
            return redirect('admin_dashboard')

    print(form.errors)
    context = {
        'application': application,
        'form': form,
        'is_admin': request.user.is_staff,
        'is_superuser': request.user.is_superuser,
    }
    return render(request, 'Application_Dash_Edit1.html', context)

##############################################################     DashBoard Delete      ####################################################################
@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='login')
@allowed_users(allowed_roles=Essco_allowed_roles)
def admin_dashboard_delete(request, pk):
    thisitem = Essco_Models.ApplicationModel.objects.get(id=pk)

    if request.method == 'POST':
        # =============================================================
        # STEP 1: Store application data BEFORE deleting
        # =============================================================
        app_name = f"{thisitem.Fname} {thisitem.Lname}"
        app_id = thisitem.ID_number
        app_email = thisitem.email
        app_pk = thisitem.pk

        # =============================================================
        # STEP 2: Get IP and location
        # =============================================================
        ip = get_client_ip(request)
        location = f"IP: {ip}"
        try:
            geo = get_geo_location(ip)
            if geo.get('city') != 'Unknown' and geo.get('country') != 'Unknown':
                location = f"{geo['city']}, {geo['country']} (IP: {ip})"
        except Exception as e:
            logger.warning(f"Could not get location for {ip}: {e}")

        # =============================================================
        # STEP 3: Delete the application
        # =============================================================
        thisitem.delete()

        logger.info(
            "APPLICATION DELETED | ID=%s | User=%s | Applicant=%s",
            pk,
            request.user.username if request.user.is_authenticated else "Anonymous",
            app_name
        )

        # =============================================================
        # STEP 4: Log the action AFTER delete (application=None)
        # =============================================================
        log_action(
            request=request,
            user=request.user if request.user.is_authenticated else "Anonymous",
            action='DELETE',
            application=None,  # ✅ Pass None since the record is deleted
            description=(
                f"Application DELETED for {app_name} "
                f"(ID: {app_id}, Email: {app_email}) from {location}"
            ),
            ip_address=ip
        )

        return redirect('admin_dashboard')

    context = {
        'items': thisitem,
        'is_admin': request.user.is_staff,
        'is_superuser': request.user.is_superuser,
    }
    return render(request, 'Application_Dash_Delete.html', context)



############################################################################################################################################################
######################################################     EMAIL PREVIEW VIEW (Dashboard)      #############################################################
############################################################################################################################################################

@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='login')
@allowed_users(allowed_roles=Essco_allowed_roles)
def preview_approval_email(request, pk):
    """Preview approval email from the dashboard."""
    application = get_object_or_404(Essco_Models.ApplicationModel, id=pk)

    # Generate email HTML
    context = {
        "application": application,
        "reference": f"ESS-{application.pk:06d}",
        "name": f"{application.Fname} {application.Lname}",
        "credit_limit": f"${application.Total_Credit_Allowed:,.2f}" if application.Total_Credit_Allowed else "TBD",
        "term": application.Term or "Not specified",
        "Deposit": f"${application.Deposit:,.2f}",
        "monthly_payment": _get_monthly_payment(application),
        "item_name": f"{application.item_name}",
        "item_sku": f"{application.item_sku}",
    }

    try:
        email_html = render_to_string("emails/application_approved.html", context)
    except Exception as e:
        logger.error(f"Error rendering email template: {e}")
        email_html = f"<p style='color:red;'>Error rendering email: {str(e)}</p>"

    context = {
        'application': application,
        'email_html': email_html,
        'is_admin': request.user.role == 'admin',
        'is_superuser': request.user.is_superuser,
        'user_role': request.user.role,
    }
    return render(request, 'emails/email_preview.html', context)


############################################################################################################################################################
#############################################     EMAIL PREVIEW VIEW for intial email (Dashboard)      #####################################################
############################################################################################################################################################

@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='login')
@allowed_users(allowed_roles=Essco_allowed_roles)
def preview_ap_initial_email(request, pk):
    """Preview approval email from the dashboard."""
    application = get_object_or_404(Essco_Models.ApplicationModel, id=pk)

    # Generate email HTML
    context = {
        "application": application,
        "reference": f"ESS-{application.pk:06d}",
        "name": f"{application.Fname} {application.Lname}",
        "credit_limit": f"${application.Total_Credit_Allowed:,.2f}" if application.Total_Credit_Allowed else "TBD",
        "term": application.Term or "Not specified",
        "Deposit": f"${application.Deposit:,.2f}",
        "monthly_payment": _get_monthly_payment(application),
    }

    try:
        email_html = render_to_string("emails/application_received_ap.html", context)
    except Exception as e:
        logger.error(f"Error rendering email template: {e}")
        email_html = f"<p style='color:red;'>Error rendering email: {str(e)}</p>"

    context = {
        'application': application,
        'email_html': email_html,
        'is_admin': request.user.role == 'admin',
        'is_superuser': request.user.is_superuser,
        'user_role': request.user.role,
    }
    return render(request, 'emails/email_preview.html', context)



############################################################################################################################################################
###################################################     SEND APPROVAL EMAIL VIEW (Dashboard)      ##########################################################
############################################################################################################################################################

@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='login')
@allowed_users(allowed_roles=Essco_allowed_roles)
def send_approval_email_view(request, pk):
    """Send approval email from the dashboard."""
    application = get_object_or_404(Essco_Models.ApplicationModel, id=pk)
    recipient_email = Essco_Emails.get_approval_recipient()

    if request.method != 'POST':
        return redirect('preview_approval_email', pk=pk)

    # Check if application is approved
    if application.Final_Approval != 'Human Approved':
        messages.error(
            request,
            "Email can only be sent for Human Approved applications. "
            f"Current status: {application.Final_Approval}"
        )
        return redirect('preview_approval_email', pk=pk)

    try:
        # ============================================================
        # DEBUG: Check if staff recipient exists
        # ============================================================
        from .models import StaffMember
        staff_count = StaffMember.objects.filter(is_approval_recipient=True, is_active=True).count()
        logger.info(f"Active staff recipients found: {staff_count}")

        if staff_count == 0:
            messages.error(request, "❌ No staff recipient configured! Please set one up in admin.")
            return redirect('preview_approval_email', pk=pk)

        # Get IP and location once for reuse
        ip = get_client_ip(request)
        location = f"IP: {ip}"
        try:
            geo = get_geo_location(ip)
            if geo.get('city') != 'Unknown' and geo.get('country') != 'Unknown':
                location = f"{geo['city']}, {geo['country']} (IP: {ip})"
        except Exception as e:
            logger.warning(f"Could not get location for {ip}: {e}")

        # ============================================================
        # SEND APPROVAL EMAIL TO APPLICANT
        # ============================================================
        applicant_email_sent = False
        applicant_error = None
        try:
            logger.info(f"Attempting to send approval email to {application.email}")
            applicant_email_sent = Essco_Emails.send_approval_email(application)
            logger.info(f"Approval email result: {applicant_email_sent}")
        except Exception as e:
            applicant_error = str(e)
            logger.error(f"Error sending approval email to applicant: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")

        # ============================================================
        # SEND STAFF NOTIFICATION EMAIL
        # ============================================================
        staff_email_sent = False
        staff_error = None
        try:
            logger.info("Attempting to send staff notification email")
            staff_email_sent = Essco_Emails.send_staff_approval_notification(application)
            logger.info(f"Staff email result: {staff_email_sent}")
        except Exception as e:
            staff_error = str(e)
            logger.error(f"Error sending staff notification email: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")

        # ============================================================
        # LOG BOTH EMAIL ATTEMPTS
        # ============================================================

        # Log applicant email attempt
        if applicant_email_sent:
            log_action(
                request=request,
                user=request.user if request.user.is_authenticated else "Anonymous",
                action='EMAIL_SENT',
                application=application,
                description=(
                    f"Approval email sent to {application.email} for "
                    f"{application.Fname} {application.Lname} (ID: {application.ID_number}) from {location}"
                ),
                ip_address=ip
            )
        else:
            error_msg = applicant_error or "Unknown error"
            log_action(
                request=request,
                user=request.user if request.user.is_authenticated else "Anonymous",
                action='EMAIL_FAILED',
                application=application,
                description=(
                    f"Failed to send approval email to {application.email} for "
                    f"{application.Fname} {application.Lname} (ID: {application.ID_number}) from {location}. "
                    f"Error: {error_msg}"
                ),
                ip_address=ip
            )

        # Log staff email attempt
        if staff_email_sent:
            log_action(
                request=request,
                user=request.user if request.user.is_authenticated else "Anonymous",
                action='EMAIL_SENT',
                application=application,
                description=(
                    f"Staff notification email sent to {recipient_email} for {application.Fname} {application.Lname} "
                    f"(ID: {application.ID_number}) approval from {location}"
                ),
                ip_address=ip
            )
        else:
            error_msg = staff_error or "Unknown error"
            log_action(
                request=request,
                user=request.user if request.user.is_authenticated else "Anonymous",
                action='EMAIL_FAILED',
                application=application,
                description=(
                    f"Failed to send staff notification email to {recipient_email} for {application.Fname} {application.Lname} "
                    f"(ID: {application.ID_number}) from {location}. "
                    f"Error: {error_msg}"
                ),
                ip_address=ip
            )

        # ============================================================
        # UPDATE STATUS AND SHOW MESSAGES
        # ============================================================
        if applicant_email_sent and staff_email_sent:
            # Update application status only if both emails sent
            application.Final_Approval = 'Human Approved'
            application.updated_by = request.user
            application.save()

            messages.success(
                request,
                f"Aproval email sent successfully to {application.email} and Staff email sent succesfully to {recipient_email}"
            )
        else:
            # Build detailed error message
            error_parts = []
            if not applicant_email_sent:
                error_parts.append(f"applicant email: {applicant_error or 'failed'}")
            if not staff_email_sent:
                error_parts.append(f"staff notification: {staff_error or 'failed'}")

            messages.error(
                request,
                f"❌ Failed to send emails: {', '.join(error_parts)}"
            )

    except Exception as e:
        logger.error(f"Unexpected error in send_approval_email_view: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        messages.error(request, f"❌ Unexpected error: {str(e)}")

    return redirect('preview_approval_email', pk=pk)

# =============================================================
# ✅ HELPER FUNCTION
# =============================================================

def _get_monthly_payment(application):
    """Helper to get monthly payment based on term."""
    if application.Term == "Six" and application.Six:
        return f"${application.Six:,.2f}"
    elif application.Term == "Twelve" and application.Twelve:
        return f"${application.Twelve:,.2f}"
    elif application.Term == "Eighteen" and application.Eighteen:
        return f"${application.Eighteen:,.2f}"
    elif application.Term == "Twenty Four" and application.Twenty_Four:
        return f"${application.Twenty_Four:,.2f}"
    elif application.Term == "Thirty" and application.Thirty:
        return f"${application.Thirty:,.2f}"
    elif application.Term == "Thirty Six" and application.Thirty_Six:
        return f"${application.Thirty_Six:,.2f}"
    return None


############################################################################################################################################################
############################################################     Analytics Dashboard      ##################################################################
############################################################################################################################################################
@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='login')
@allowed_users(allowed_roles=Essco_allowed_roles)
def analytics_dashboard(request):
    # Get date range from request
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    # Base queryset
    applications = Essco_Models.ApplicationModel.objects.all()

    # Apply date filters
    if date_from:
        applications = applications.filter(created__gte=date_from)
    if date_to:
        applications = applications.filter(created__lte=date_to)

    # Stats
    total = applications.count()
    approved = applications.filter(Final_Approval='Human Approved').count()
    approved_pending = applications.filter(Approval_Status='Approved Pending').count()
    human_review  = applications.filter(Approval_Status='Human Review').count()
    rejected = applications.filter(Approval_Status='Rejected').count()
    review = applications.filter(Approval_Status='Review').count()
    draft = applications.filter(Approval_Status='Draft').count() ############################## unused

    # Income stats
    total_income = applications.aggregate(Sum('Disposable_Income_After'))['Disposable_Income_After__sum'] or 0
    avg_income = applications.aggregate(Avg('Gross_Monthly_Income_AT'))['Gross_Monthly_Income_AT__avg'] or 0

    # Additional metrics
    unique_users = applications.values('email').distinct().count()
    avg_age = applications.aggregate(Avg('age'))['age__avg'] or 0

    if total > 0:
        avg_reject = (rejected / total) * 100
    else:
        avg_reject = 0

    avg_debt_ratio = applications.aggregate(Avg('Debt_To_Income_Ratio'))['Debt_To_Income_Ratio__avg'] or 0
    avg_debt_ratio = round(avg_debt_ratio, 2)
    total_credit_allowed = applications.aggregate(Sum('Total_Credit_Allowed'))['Total_Credit_Allowed__sum'] or 0

    # Employment length distribution
    employment_lengths = {
        '< 6mo': applications.filter(Len_Employ__icontains='Less than 6 months').count(),
        '6-12mo': applications.filter(Len_Employ__icontains='6 months to 2 years').count(),
        '1-2yr': applications.filter(Len_Employ__icontains='2 + Years').count(),
        '2-5yr': applications.filter(Len_Employ__icontains='2-5 years').count(),
        '5-10yr': applications.filter(Len_Employ__icontains='5-10 years').count(),
        '10+yr': applications.filter(Len_Employ__icontains='10+ years').count(),
    }

    # Income distribution
    income_ranges = {
        '$0-$1k': applications.filter(Gross_Monthly_Income_AT__lt=1000).count(),
        '$1k-$2k': applications.filter(Gross_Monthly_Income_AT__gte=1000, Gross_Monthly_Income_AT__lt=2000).count(),
        '$2k-$3k': applications.filter(Gross_Monthly_Income_AT__gte=2000, Gross_Monthly_Income_AT__lt=3000).count(),
        '$3k-$5k': applications.filter(Gross_Monthly_Income_AT__gte=3000, Gross_Monthly_Income_AT__lt=5000).count(),
        '$5k+': applications.filter(Gross_Monthly_Income_AT__gte=5000).count(),
    }

    # Recent activity
    recent_activities = AuditLog.objects.select_related('user', 'application').order_by('-created')[:10]

    # Trend data (last 7 days)
    today = datetime.now().date()
    trend_labels = []
    trend_data = []
    trend_approved = []

    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        trend_labels.append(date.strftime('%a'))
        day_count = applications.filter(created__date=date).count()
        day_approved = applications.filter(created__date=date, Approval_Status='Approved').count()
        trend_data.append(day_count)
        trend_approved.append(day_approved)

    context = {
        # Stats
        'total_applications': total,
        'approved_count': approved,
        'approved_pending_count': approved_pending,
        'human_review_count':human_review,
        'rejected_count': rejected,
        'review_count': review,
        'draft_count': draft,  #################################unused

        # Income
        'total_income': total_income,
        'avg_income': avg_income,

        # Additional metrics
        'unique_users': unique_users,
        'avg_age': avg_age,
        'avg_debt_ratio': avg_debt_ratio,
        'total_credit_allowed': total_credit_allowed,
        'pending_review': review,

        # Percentages for progress bars
        #'approval_percentage': (approved / total * 100) if total > 0 else 0, round(avg_debt_ratio, 2)
        'approval_percentage': round((approved / total * 100) if total > 0 else 0, 2),
        'pending_percentage': round(((approved_pending + human_review) / total * 100) if total > 0 else 0, 2),
        'rejection_percentage': round((rejected / total * 100) if total > 0 else 0, 2),


        # Chart data
        'trend_labels': trend_labels,
        'trend_data': trend_data,
        'trend_approved': trend_approved,

        'income_labels': list(income_ranges.keys()),
        'income_data': list(income_ranges.values()),

        'employment_labels': list(employment_lengths.keys()),
        'employment_data': list(employment_lengths.values()),

        # Recent activity
        'recent_activities': recent_activities,

        # Date range
        'date_from': date_from,
        'date_to': date_to,
    }

    return render(request, 'analytics.html', context)


############################################################################################################################################################
############################################################     Team Page Dashboard      ##################################################################
############################################################################################################################################################

@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='login')
@allowed_users(allowed_roles=Essco_allowed_roles)
def team_page(request):
    """
    Display team members with filtering and statistics
    """
    try:
        logger = logging.getLogger(__name__)
        logger.info(f"Team page accessed by user: {request.user.username}")

        # Get all active staff members
        team_members = Essco_Models.StaffMember.objects.filter(is_active=True)

        # Get approval recipients separately (highlight them)
        approval_recipients = team_members.filter(is_approval_recipient=True)

        # Group by role for statistics
        role_stats = (
            team_members
            .values('role')
            .annotate(count=Count('id'))
            .order_by('role')
        )

        # Get role display names for the template
        # Use the model's ROLE_CHOICES
        if hasattr(Essco_Models.StaffMember, 'ROLE_CHOICES'):
            role_display = dict(Essco_Models.StaffMember.ROLE_CHOICES)
        else:
            # Fallback if ROLE_CHOICES doesn't exist
            role_display = {
                'manager': 'Manager',
                'supervisor': 'Supervisor',
                'agent': 'Agent',
                'admin': 'Admin',
                'other': 'Other',
            }

        for stat in role_stats:
            stat['role_display'] = role_display.get(stat['role'], stat['role'].title())

        # Get total counts
        total_members = team_members.count()
        total_approval_recipients = approval_recipients.count()

        context = {
            'team_members': team_members,
            'approval_recipients': approval_recipients,
            'role_stats': role_stats,
            'total_members': total_members,
            'total_approval_recipients': total_approval_recipients,
            'title': 'Our Team',
        }

        return render(request, 'team.html', context)

    except Exception as e:
        # Log the full error
        logger = logging.getLogger(__name__)
        logger.error(f"Team page error: {str(e)}")
        logger.error(traceback.format_exc())

        # Return a friendly error page
        context = {
            'error': 'Unable to load team members. Please try again later.',
            'title': 'Error'
        }
        return render(request, 'error.html', context, status=500)


############################################################################################################################################################
#############################################################     Settings Dashboard      ##################################################################
############################################################################################################################################################
@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='login')
@allowed_users(allowed_roles=Essco_allowed_roles)
def settings(request):
    """Maintenance mode settings"""
    settings = SiteSettings.get_settings()

    if request.method == 'POST':
        form = MaintenanceSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            settings = form.save(commit=False)
            settings.updated_by = request.user.username
            settings.save()
            messages.success(request, "✅ Maintenance settings updated successfully!")
            return redirect('maintenance_settings')
    else:
        form = MaintenanceSettingsForm(instance=settings)

    context = {
        'form': form,
        'settings': settings,
        'title': 'Maintenance Settings',
        'is_admin': request.user.role == 'admin',
    }
    return render(request, 'settings.html', context)


# ===== FUTURE TILES =====
# Uncomment and implement when ready

# @never_cache
# @cache_control(no_cache=True, must_revalidate=True, no_store=True)
# @login_required(login_url='login')
# @allowed_users(allowed_roles=Essco_allowed_roles)
# def general_settings(request):
#     """General site settings"""
#     # Your code here
#     pass

# @never_cache
# @cache_control(no_cache=True, must_revalidate=True, no_store=True)
# @login_required(login_url='login')
# @allowed_users(allowed_roles=Essco_allowed_roles)
# def email_settings(request):
#     """Email configuration settings"""
#     # Your code here
#     pass

# @never_cache
# @cache_control(no_cache=True, must_revalidate=True, no_store=True)
# @login_required(login_url='login')
# @allowed_users(allowed_roles=Essco_allowed_roles)
# def loan_settings(request):
#     """Loan configuration settings"""
#     # Your code here
#     pass


############################################################################################################################################################
######################################################     MAINTENANCE SETTINGS CONFIGURATION PAGE      ####################################################
############################################################################################################################################################
@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='login')
@allowed_users(allowed_roles=Essco_allowed_roles)
def maintenance_settings(request):
    """Maintenance mode settings configuration page"""
    settings = SiteSettings.get_settings()

    if request.method == 'POST':
        form = MaintenanceSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            settings = form.save(commit=False)
            settings.updated_by = request.user.username
            settings.save()
            messages.success(request, "✅ Maintenance settings updated successfully!")

            # Log the action
            from audit.services import log_action, get_client_ip
            log_action(
                request=request,
                user=request.user,
                action='UPDATE',
                application=None,
                description=f"Maintenance settings updated by {request.user.username}. Mode: {'ON' if settings.maintenance_mode else 'OFF'}",
                ip_address=get_client_ip(request)
            )

            return redirect('maintenance_settings')
        else:
            messages.error(request, "❌ Please correct the errors below.")
    else:
        form = MaintenanceSettingsForm(instance=settings)

    context = {
        'form': form,
        'settings': settings,
        'title': 'Maintenance Settings',
        'is_admin': request.user.role == 'admin',
        'is_superuser': request.user.is_superuser,
    }
    return render(request, 'maintenance_tile.html', context)

############################################################################################################################################################
######################################################     MAINTENANCE SETTINGS Rates PAGE      ####################################################
############################################################################################################################################################
@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='login')
@allowed_users(allowed_roles=Essco_allowed_roles)
def rates(request):
    rates = Essco_Models.InterestRate.objects.all()
    active_count = rates.filter(is_active=True).count()
    inactive_count = rates.filter(is_active=False).count()

    context = {
        'rates': rates,
        'active_count': active_count,
        'inactive_count': inactive_count,
    }
    return render(request, 'rates.html', context)

@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='login')
@allowed_users(allowed_roles=Essco_allowed_roles)
def interest_rate_edit(request, pk):
    log = Essco_Models.InterestRate.objects.get(id=pk)
    rates = Essco_Models.InterestRate.objects.filter(id=pk)
    form = Essco_Forms.RatesForm(instance=log)

    if request.method == 'POST':
        form = Essco_Forms.RatesForm(request.POST, instance=log)
        if form.is_valid():
            form.save()
            return redirect('rates')
        print(form.errors)
    context = {'LogInfo':log, 'rates':rates, 'form':form}
    return render(request, 'rates_edit.html', context)

############################################################################################################################################################
#############################################################     CUSTOMER DASHBOARD      ##################################################################
############################################################################################################################################################

@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@customer_required
def customer_dashboard(request):
    """Customer dashboard view - only accessible to users with customer role"""

    # 1. Get the user from request
    user = request.user

    # 2. ✅ Use helper to get ONLY this user's applications
    # This uses the customer foreign key, NOT email
    applications = get_user_applications(user)

    # 3. ✅ Get consistent context using helper
    context = get_customer_context(user)

    # 4. Add any view-specific context
    context.update({
        'dashboard_title': 'My Applications',
        'show_application_actions': True,
        'user_email': user.email,  # Keep for display
    })

    return render(request, 'customer_dashboard.html', context)




############################################################################################################################################################
#######################################################     CUSTOMER DASHBOARD Applications      ###########################################################
############################################################################################################################################################
@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
@customer_required
def customer_dashboard_apps(request):
    """
    View that:
    1. Gets the current user from request
    2. Gets the associated email of the user
    3. ✅ Securely filters applications using the customer foreign key

    Sean can ONLY see Sean's applications.
    Bob can ONLY see Bob's applications.
    """
    # 1. Get the user from request
    user = request.user

    # 2. ✅ Use helper to get ONLY this user's applications
    # This uses the customer foreign key, NOT email
    applications = get_user_applications(user)

    # 3. ✅ Get consistent context using helper
    context = get_customer_context(user)

    # 4. Add any view-specific context
    context.update({
        'dashboard_title': 'My Applications',
        'show_application_actions': True,
        'user_email': user.email,  # Keep for display
    })

    return render(request, 'customer_applications_list.html', context)

############################################################################################################################################################
#######################################################     CUSTOMER DASHBOARD Application Edit      ########################################################
############################################################################################################################################################
@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
@customer_required
def customer_dashboard_apps_edit(request, application_id):
    """
    Edit view using a Django form.

    ✅ Uses the customer foreign key (not email) for security
    ✅ Uses helpers for permission checks
    ✅ Staff and superusers can edit any application
    ✅ Regular users can ONLY edit their own applications
    """
    user = request.user

    # ✅ Use helper with permission check (not email filter)
    # This raises 404 if not found, 403 if user doesn't own it
    application = get_user_application(application_id, user)

    # ✅ Check if user can edit this application
    if not ApplicationPermissions.can_edit(user, application):
        messages.error(request, "You don't have permission to edit this application.")
        return redirect('customer_dashboard_apps')

    if request.method == 'POST':
        form = Essco_Forms.ApplicationForm(request.POST, request.FILES, instance=application)
        if form.is_valid():
            form.save()
            messages.success(request, 'Application updated successfully!')
            return redirect('customer_dashboard_apps')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = Essco_Forms.ApplicationForm(instance=application)

    context = {
        'form': form,
        'application': application,
        'user_email': user.email,
    }

    return render(request, 'customer_application_edit.html', context)

############################################################################################################################################################
#######################################################     CUSTOMER DASHBOARD Link Applications      ########################################################
############################################################################################################################################################

@never_cache
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
@customer_required
def link_application(request):
    """
    🔒 SECURE: Users can ONLY link applications that:
    1. Match their email address
    2. Are unlinked (customer__isnull=True)
    3. Match the ID number they enter
    """
    # ⭐ User must have a valid email
    if not request.user.email:
        messages.error(request, "Your account doesn't have an email address.")
        return redirect('customer_dashboard_apps')

    # ⭐ Check existing applications
    unlinked_apps = Essco_Models.ApplicationModel.objects.filter(
        email__iexact=request.user.email,
        customer__isnull=True
    )

    linked_apps = Essco_Models.ApplicationModel.objects.filter(
        customer=request.user
    )

    # ⭐ Show status messages
    if not unlinked_apps.exists() and not linked_apps.exists():
        messages.info(
            request,
            "We couldn't find any applications associated with your email address."
        )
    elif linked_apps.exists() and not unlinked_apps.exists():
        messages.info(
            request,
            f"You already have {linked_apps.count()} application(s) linked to your account."
        )

    if request.method == 'POST':
        id_number = request.POST.get('id_number', '').strip()

        # ⭐ Validate input
        if not id_number:
            messages.error(request, "Please enter your ID number.")
            return render(request, 'link_application.html')

        # ⭐ Clean the ID number (remove ALL non-numeric)
        cleaned_input = ''.join(filter(str.isdigit, id_number))

        # ⭐ 🔒 CRITICAL: ONLY search for applications with THIS user's email
        possible_apps = Essco_Models.ApplicationModel.objects.filter(
            email__iexact=request.user.email,  # ⭐ MUST match user's email
            customer__isnull=True              # ⭐ MUST be unlinked
        )

        # ⭐ 🔒 Security: Rate limiting (optional but recommended)
        # Prevent brute force attempts
        from django.core.cache import cache
        cache_key = f"link_attempts_{request.user.id}"
        attempts = cache.get(cache_key, 0)
        if attempts > 5:  # Max 5 attempts per hour
            messages.error(
                request,
                "Too many attempts. Please try again later or contact support."
            )
            return render(request, 'link_application.html')
        cache.set(cache_key, attempts + 1, 3600)  # 1 hour expiry

        # ⭐ 🔒 Security: Log the attempt
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"🔒 LINK ATTEMPT: User={request.user.email}, "
            f"ID={id_number}, "
            f"Found={possible_apps.count()} unlinked apps"
        )

        # ⭐ Try to find a match
        matched_app = None
        for app in possible_apps:
            db_cleaned = ''.join(filter(str.isdigit, str(app.ID_number)))
            if db_cleaned == cleaned_input:
                matched_app = app
                break

        if matched_app:
            # ⭐ 🔒 FINAL SECURITY CHECK: Ensure the email matches
            if matched_app.email.lower() != request.user.email.lower():
                # 🚨 This should never happen, but just in case
                logger.error(
                    f"🚨 SECURITY ALERT: Email mismatch! "
                    f"App: {matched_app.email}, User: {request.user.email}"
                )
                messages.error(request, "Security check failed. Please contact support.")
                return render(request, 'link_application.html')

            # ⭐ 🔒 Check if already linked
            if matched_app.customer and matched_app.customer != request.user:
                logger.warning(
                    f"🔒 LINK BLOCKED: App {matched_app.id} already linked to "
                    f"{matched_app.customer.email}"
                )
                messages.warning(
                    request,
                    "This application is already linked to another account."
                )
                return render(request, 'link_application.html')

            # ✅ All checks passed - Link the application
            matched_app.customer = request.user
            matched_app.save()

            # ⭐ Log success
            logger.info(
                f"✅ LINK SUCCESS: App {matched_app.id} linked to {request.user.email}"
            )

            messages.success(
                request,
                f"✅ Application for {matched_app.Fname} {matched_app.Lname} has been linked!"
            )
            log_action(
                request=request,
                user=request.user,
                action='LINK_APPLICATION',
                application=matched_app,
                description=f"Application {matched_app.reference_number} linked to user",
                ip_address=request.META.get('REMOTE_ADDR')
            )

            return redirect('customer_dashboard_apps')
        else:
            # ⭐ No match found
            messages.error(
                request,
                f"No unlinked application found with ID number '{id_number}'. "
                f"Please check your ID number or contact support."
            )
            return render(request, 'link_application.html')

    context = {
        'unlinked_count': unlinked_apps.count(),
        'linked_count': linked_apps.count(),
        'has_unlinked': unlinked_apps.exists(),
        'has_linked': linked_apps.exists(),
        'user_email': request.user.email,
    }
    return render(request, 'link_application.html', context)


#############################################################################################################################################################
####################################################    Pay Deposit    ######################################################################################
#############################################################################################################################################################
@transaction.atomic
@login_required
def pay_deposit(request, application_id):
    """
    Pay deposit and auto-create loan (Production version)
    """
    application = get_object_or_404(Essco_Models.ApplicationModel, id=application_id)

    # Security: Check if user owns this application
    if request.user != application.customer and not request.user.is_staff:
        messages.error(request, "You don't have permission to pay this deposit.")
        return redirect('customer_dashboard_apps')

    # ✅ Security: Check if application is approved using Final_Approval
    if application.Final_Approval not in ['Human Approved', 'Approved Pending']:
        messages.error(request, "This application is not approved for deposit payment.")
        return redirect('customer_dashboard_apps')

    # Security: Check if deposit already paid
    if application.deposit_status == 'PAID':
        messages.warning(request, "Deposit already paid for this application.")
        return redirect('customer_dashboard_apps')

    # Security: Check if loan already exists
    if hasattr(application, 'created_loan') and application.created_loan.exists():
        messages.warning(request, "A loan has already been created from this application.")
        return redirect('loans:loan_detail', loan_id=application.created_loan.first().id)

    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount', 0))

        if amount <= 0:
            messages.error(request, "Please enter a valid deposit amount.")
            return redirect('pay_deposit', application_id=application.id)

        try:
            # 1. Get payment method
            payment_method_id = request.POST.get('payment_method')
            payment_method = get_object_or_404(PaymentMethod, id=payment_method_id)

            # 2. Create payment record
            payment = PaymentRecord.objects.create(
                customer=request.user,
                application=application,
                recorded_by=request.user,
                category='DEPOSIT',
                amount=amount,
                payment_method=payment_method,
                #receipt_number=f"DEP-{timezone.now().strftime('%Y%m%d')}-{PaymentRecord.objects.count() + 1:06d}",
                receipt_number=f"DP-{timezone.now().strftime('%H%M%S')}-{PaymentRecord.objects.count() + 1:03d}",
                status='PENDING',
                confirmed_by=request.user,
                confirmed_at=timezone.now(),
                auto_create_loan=True,
                notes=f"Deposit paid for application {application.reference_number}"
            )

            # Call confirm() to trigger customer creation
            payment.confirm(request.user)

            # 3. Update application with deposit info
            application.deposit_paid = amount
            application.deposit_paid_date = timezone.now()
            application.deposit_payment_method = payment_method.name
            application.deposit_status = 'PAID'
            application.deposit_receipt_number = payment.receipt_number
            application.deposit_payment = payment
            application.save()

            # 4. Auto-create loan
            loan = LoanCreationService.handle_deposit_confirmation(payment)

            if loan:
                #UPDATE LOAN TOTAL PAID WITH DEPOSIT
                loan.total_paid = loan.deposit_paid  # The deposit amount
                loan.outstanding_balance = loan.total_payable - loan.total_paid
                loan.save()

                messages.success(
                    request,
                    f"✅ Deposit of ${amount} paid successfully!\n"
                    f"🚀 Loan {loan.loan_id} has been auto-created and activated!"
                )

                log_action(
                    request=request,
                    user=request.user,
                    action='DEPOSIT_RECEIVED',
                    description=f"Deposit of ${amount} paid for application {application.reference_number} and Loan {loan.loan_id} has been auto-created and activated!",
                    application=application,  # ✅ Already has this
                    loan=loan,  # ✅ ADD THIS (if loan exists)
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                return redirect('loans:loan_detail', loan_id=loan.id)
            else:
                messages.success(
                    request,
                    f"✅ Deposit of ${amount} paid successfully!\n"
                    f"Loan will be created shortly."
                )
                log_action(
                    request=request,
                    user=request.user,
                    action='ERROR',
                    description=f"Deposit of ${amount} paid for application {application.reference_number}, Loan will be created shortly",
                    application=application,  # ✅ Already has this
                    loan=loan,  # ✅ ADD THIS (if loan exists)
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                return redirect('customer_dashboard_apps')

        except Exception as e:
            error_msg = str(e)
            messages.error(request, f"Failed to process deposit: {str(e)}")
            log_action(
                request=request,
                user=request.user,
                action='ERROR',
                description=f"Failed to process deposit for application {application.reference_number}: {error_msg}",
                loan=loan,
                ip_address=request.META.get('REMOTE_ADDR')
            )

    # GET request - show payment form
    suggested_deposit = application.Purchase_Value * Decimal('0.10')
    payment_methods = PaymentMethod.objects.filter(is_active=True)

    context = {
        'application': application,
        'suggested_deposit': suggested_deposit,
        'payment_methods': payment_methods,
        'deposit_required': suggested_deposit,
    }
    return render(request, 'pay_deposit.html', context)


#############################################################################################################################################################
####################################################    Manually Create Loan    #############################################################################
#############################################################################################################################################################

@login_required
@officer_required
def manual_create_loan(request, application_id):
    """
    Manually create a loan from an application (for staff use).

    The view handles the HTTP request.
    LoanCreationService handles the actual loan creation/calculation.
    """

    application = get_object_or_404(Essco_Models.ApplicationModel, id=application_id)

    # ============================================================
    # CHECK IF LOAN ALREADY EXISTS
    # ============================================================
    existing_loan = LoanProduct.objects.filter(application=application).first()

    if existing_loan:
        messages.warning(request, f"A loan already exists for this application: "  f"{existing_loan.loan_id}" )

        # Go back to the application instead of customer loan page
        return redirect('admin_dashboard_edit', application.id)

    # ============================================================
    # CHECK DEPOSIT
    # ============================================================
    if application.deposit_paid <= 0:
        messages.error(request, "No deposit has been paid for this application.")

        return redirect('admin_dashboard_edit', application.id)

    # ============================================================
    # GET PAYMENT RECORD
    # ============================================================
    payment = None

    if application.deposit_payment_id:
        payment = PaymentRecord.objects.filter(id=application.deposit_payment_id).first()

    if not payment:
        messages.error(request, "No payment record found for this application.")

        return redirect('admin_dashboard_edit', application.id)

    # ============================================================
    # POST - CREATE LOAN
    # ============================================================
    if request.method == 'POST':

        try:
            from loans.services.loan_creation_service import (  LoanCreationService )

            # ----------------------------------------------------
            # Get loan terms from form
            # ----------------------------------------------------

            principal = Decimal(
                request.POST.get('principal_amount',application.Financed_Amt or application.Purchase_Value)
            )

            interest_rate = Decimal(
                request.POST.get('interest_rate', '12.0')
            )

            tenure_months = int(
                request.POST.get('tenure_months', 24)
            )

            # ----------------------------------------------------
            # Create loan through service
            # ----------------------------------------------------

            loan = LoanCreationService.manual_create_loan(
                application=application,
                payment=payment,
                principal=principal,
                interest_rate=interest_rate,
                tenure_months=tenure_months,
                user=request.user
            )

            # ====================================================
            # SUCCESS
            # ====================================================

            if loan:

                # Mark deposit as transferred
                application.deposit_status = 'TRANSFERRED'
                application.save(
                    update_fields=['deposit_status']
                )

                messages.success(
                    request,
                    f"Loan {loan.loan_id} created successfully. "
                    f"Principal: ${principal:,.2f} | "
                    f"Interest: {interest_rate}% | "
                    f"Term: {tenure_months} months"
                )

                return redirect('staff_loan_detail',loan_id=loan.id)

                # ------------------------------------------------
                # Audit log
                # ------------------------------------------------

                log_action(
                    request=request,
                    user=request.user,
                    action='LOAN_CREATED',
                    description=(
                        f"{loan.loan_id} Loan created manually successfully. "
                        f"Principal: ${principal:,.2f} | "
                        f"Interest Rate: {interest_rate}% | "
                        f"Tenure: {tenure_months} months"
                    ),
                    application=application,
                    loan=loan,
                    ip_address=request.META.get('REMOTE_ADDR')
                )

                # ------------------------------------------------
                # IMPORTANT:
                # Do NOT send user to loans:loan_detail
                #
                # Send them back to the application/admin page.
                # ------------------------------------------------

                #return redirect('admin_dashboard_edit', application.id)
                return redirect('loans:loan_detail', loan_id=loan.id)

            else:

                messages.error(
                    request,
                    "Failed to create loan. Please check the logs."
                )

        except Exception as e:

            error_msg = str(e)

            messages.error(
                request,
                f"Error creating loan: {error_msg}"
            )

            log_action(
                request=request,
                user=request.user,
                action='ERROR',
                description=(
                    f"Error creating loan: {error_msg}"
                ),
                loan=None,
                application=application,
                ip_address=request.META.get('REMOTE_ADDR')
            )

    # ============================================================
    # GET - SHOW MANUAL LOAN FORM
    # ============================================================

    context = {
        'application': application,
        'payment': payment,
        'default_principal': (
            application.Financed_Amt
            or application.Purchase_Value
        ),
        'default_interest': Decimal('12.00'),
        'default_tenure': 24,
        'deposit_amount': application.deposit_paid,
    }

    return render(
        request,
        'manual_create_loan.html',
        context
    )



@login_required
@officer_required  # Only staff can access this
def manual_create_loan1(request, application_id):
    """
    Manually create a loan from an application (for staff use)
    This handles cases where auto-creation failed
    """
    application = get_object_or_404(Essco_Models.ApplicationModel, id=application_id)

    # Check if loan already exists
    existing_loan = LoanProduct.objects.filter(application=application).first()
    if existing_loan:
        messages.warning(request, f"A loan already exists for this application: {existing_loan.loan_id}")
        return redirect('loans:loan_detail', loan_id=existing_loan.id)

    # Check if deposit is paid
    if application.deposit_paid <= 0:
        messages.error(request, "No deposit has been paid for this application.")
        return redirect('customer_dashboard_apps')

    # Get the payment record
    payment = None
    if application.deposit_payment_id:
        payment = PaymentRecord.objects.filter(id=application.deposit_payment_id).first()

    if not payment:
        messages.error(request, "No payment record found for this application.")
        return redirect('customer_dashboard_apps')

    if request.method == 'POST':
        try:
            # Get loan terms from form (with defaults from application)
            principal = Decimal(request.POST.get('principal_amount', application.Financed_Amt or application.Purchase_Value))
            interest_rate = Decimal(request.POST.get('interest_rate', 12.0))
            tenure_months = int(request.POST.get('tenure_months', 24))

            # Create loan using the service
            from loans.services.loan_creation_service import LoanCreationService

            # Override the service to use manual values
            loan = LoanCreationService.manual_create_loan(
                application=application,
                payment=payment,
                principal=principal,
                interest_rate=interest_rate,
                tenure_months=tenure_months,
                user=request.user
            )

            if loan:
                # Update application status
                application.deposit_status = 'TRANSFERRED'
                application.save()

                messages.success(
                    request,
                    f"✅ Loan {loan.loan_id} created manually successfully!\n"
                    f"Principal: ${principal}\n"
                    f"Interest Rate: {interest_rate}%\n"
                    f"Tenure: {tenure_months} months"
                )
                log_action(
                    request=request,
                    user=request.user,
                    action='LOAN_CREATED',
                    description=f"{loan.loan_id} Loan created manually successfully, Principal:- ${principal}\n |  Interest Rate:- {interest_rate}%\n | Tenure:- {tenure_months} months",
                    application=application,
                    loan=loan,  # ✅ ADD THIS
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                return redirect('loans:loan_detail', loan_id=loan.id)
            else:
                messages.error(request, "Failed to create loan. Please check the logs.")

        except Exception as e:
            error_msg = str(e)
            messages.error(request, f"Error creating loan: {str(e)}")
            log_action(
                request=request,
                user=request.user,
                action='ERROR',
                description=f"Error creating loan: {str(e)} | {error_msg}",
                loan=None,
                application=application,
                ip_address=request.META.get('REMOTE_ADDR')
            )

    # GET request - show form with default values
    context = {
        'application': application,
        'payment': payment,
        'default_principal': application.Financed_Amt or application.Purchase_Value,
        'default_interest': 12.0,  # Default or from application
        'default_tenure': 24,  # Default
        'deposit_amount': application.deposit_paid,
    }
    return render(request, 'manual_create_loan.html', context)

#############################################################################################################################################################
#########################################################    Staff Loan List    #############################################################################
#############################################################################################################################################################

# applications/views.py - Add this view
@login_required
@officer_required
def staff_loan_list(request):
    """
    Staff view to see all loans and applications with pagination and search.
    """
    from django.core.paginator import Paginator
    from django.db.models import Q, Sum

    # ---------------------------------------------------------
    # Base Querysets
    # ---------------------------------------------------------
    loans = LoanProduct.objects.all().order_by('-created_at')

    pending_loan_applications = Essco_Models.ApplicationModel.objects.filter(
        deposit_status='PAID',
        Final_Approval='Human Approved'
    ).exclude(
        id__in=LoanProduct.objects.values_list('application_id', flat=True)
    )

    # ---------------------------------------------------------
    # Search & Filtering
    # ---------------------------------------------------------
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()

    if search_query:
        loans = loans.filter(
            Q(loan_id__icontains=search_query) |
            Q(customer__first_name__icontains=search_query) |
            Q(customer__last_name__icontains=search_query) |
            Q(customer__email__icontains=search_query) |
            Q(application__reference_number__icontains=search_query)
        )

    if status_filter:
        loans = loans.filter(status=status_filter)

    # ---------------------------------------------------------
    # Pagination
    # ---------------------------------------------------------
    paginator = Paginator(loans, 25)  # 25 loans per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # ---------------------------------------------------------
    # Statistics
    # ---------------------------------------------------------
    total_loans = LoanProduct.objects.count()
    active_loans = LoanProduct.objects.filter(status='ACTIVE').count()
    paid_off_loans = LoanProduct.objects.filter(status='PAID_OFF').count()
    total_outstanding = LoanProduct.objects.aggregate(Sum('outstanding_balance'))['outstanding_balance__sum'] or 0

    # ---------------------------------------------------------
    # Context
    # ---------------------------------------------------------
    context = {
        'loans': page_obj,                     # ✅ Paginated loans
        'page_obj': page_obj,                  # ✅ For template pagination controls
        'pending_loan_applications': pending_loan_applications,
        'search_query': search_query,
        'status_filter': status_filter,
        'status_choices': LoanProduct.STATUS_CHOICES,
        'total_loans': total_loans,
        'active_loans': active_loans,
        'paid_off_loans': paid_off_loans,
        'pending_count': pending_loan_applications.count(),
        'total_outstanding': total_outstanding,
    }
    return render(request, 'staff_loan_list.html', context)





@login_required
@officer_required  # Only staff can access this
def staff_loan_list1(request):
    """
    Staff view to see all loans and applications
    """
    # Get all loans
    loans = LoanProduct.objects.all().order_by('-created_at')

    # Get applications with deposit paid but no loan (for manual creation)
    pending_loan_applications = Essco_Models.ApplicationModel.objects.filter(
        deposit_status='PAID',
        Final_Approval='Human Approved'
    ).exclude(
        id__in=LoanProduct.objects.values_list('application_id', flat=True)
    )

    context = {
        'loans': loans,
        'pending_loan_applications': pending_loan_applications,
        'total_loans': loans.count(),
        'active_loans': loans.filter(status='ACTIVE').count(),
        'pending_count': pending_loan_applications.count(),
        'total_outstanding': loans.aggregate(Sum('outstanding_balance'))['outstanding_balance__sum'] or 0,
    }
    return render(request, 'staff_loan_list.html', context)

#############################################################################################################################

# applications/views.py or loans/views.py

@login_required
@officer_required  # Only staff can access this
def staff_loan_detail(request, loan_id):
    """
    Staff view for loan details
    """
    loan = get_object_or_404(LoanProduct, id=loan_id)

    # Get payment schedule
    schedule = loan.payment_schedule.all().order_by('due_date')

    # Get payments
    payments = loan.payments.all().order_by('-created_at')

    # Get customer info from the application
    application = loan.application

    if application:
        customer_name = f"{application.Fname} {application.Lname}"
        customer_email = application.email
        customer_phone = application.Cell_Phone
    else:
        customer_name = "No application"
        customer_email = "No email"
        customer_phone = "No phone"

    # ==========================================
    # ✅ DEPOSIT INFORMATION
    # ==========================================
    deposit_target = loan.deposit_target or 0
    deposit_paid = loan.deposit_paid or 0
    deposit_complete = loan.deposit_complete
    deposit_remaining = max(deposit_target - deposit_paid, 0)

    # Calculate deposit percentage
    if deposit_target > 0:
        deposit_percentage = (deposit_paid / deposit_target) * 100
    else:
        deposit_percentage = 0

    # Check if deposit was reversed
    deposit_reversed = False
    if loan.deposit_payment and loan.deposit_payment.is_reversed:
        deposit_reversed = True

    # Get active deposit payment (if any)
    active_deposit = None
    if loan.deposit_payment and not loan.deposit_payment.is_reversed:
        active_deposit = loan.deposit_payment

    # ==========================================
    # ✅ CALCULATE FINANCIALS
    # ==========================================
    total_paid = loan.total_paid or 0
    outstanding_balance = loan.outstanding_balance or 0
    total_payable = loan.total_payable or 0

    # Count active payments (not reversed)
    active_payments = payments.filter(is_reversed=False)

    context = {
        'loan': loan,
        'customer_name': customer_name,
        'customer_email': customer_email,
        'customer_phone': customer_phone,
        'has_account': bool(loan.customer),
        'schedule': schedule,
        'payments': payments,
        'active_payments': active_payments,
        'customer': loan.customer,
        'application': loan.application,

        # ✅ Deposit context
        'deposit_target': deposit_target,
        'deposit_paid': deposit_paid,
        'deposit_complete': deposit_complete,
        'deposit_remaining': deposit_remaining,
        'deposit_percentage': deposit_percentage,
        'deposit_reversed': deposit_reversed,
        'active_deposit': active_deposit,

        # ✅ Financial summary
        'total_paid': total_paid,
        'outstanding_balance': outstanding_balance,
        'total_payable': total_payable,
        'payment_count': active_payments.count(),
    }
    return render(request, 'staff_loan_detail.html', context)




@login_required
@officer_required  # Only staff can access this
def staff_loan_detail1(request, loan_id):
    """
    Staff view for loan details
    """
    loan = get_object_or_404(LoanProduct, id=loan_id)

    # Get payment schedule
    schedule = loan.payment_schedule.all().order_by('due_date')

    # Get payments
    payments = loan.payments.all().order_by('-created_at')

    #Get customer info from the application
    application = loan.application

    if application:
        customer_name = f"{application.Fname} {application.Lname}"
        customer_email = application.email

    else:
        customer_name = "No application"
        customer_email = "No email"


    context = {
        'loan': loan,
        'customer_name': customer_name,
        'customer_email': customer_email,

        'has_account': bool(loan.customer),
        'schedule': schedule,
        'payments': payments,
        'customer': loan.customer,
        'application': loan.application,
    }
    return render(request, 'staff_loan_detail.html', context)


# applications/views.py - Add this view

@login_required
@officer_required  # Only staff can access this
def staff_loan_pending(request):
    """
    Staff view for pending loans (deposit paid, no loan created)
    """
    pending_applications = Essco_Models.ApplicationModel.objects.filter(
        deposit_status='PAID',
        Final_Approval='Human Approved'
    ).exclude(
        id__in=LoanProduct.objects.values_list('application_id', flat=True)
    ).order_by('-created')

    context = {
        'pending_applications': pending_applications,
        'count': pending_applications.count(),
    }
    return render(request, 'staff_loan_pending.html', context)




# applications/views.py

@login_required
@officer_required
def admin_link_application(request):
    """
    Admin view to manually link an application to a user
    With proper checks and validation
    """
    if request.method == 'POST':
        application_id = request.POST.get('application_id')
        user_id = request.POST.get('user_id')
        confirm = request.POST.get('confirm', '')

        # ✅ Check 1: Both fields are provided
        if not application_id or not user_id:
            messages.error(request, "Please select both application and user.")
            return redirect('admin_link_application')

        # ✅ Check 2: Confirmation checkbox is checked
        if confirm != 'yes':
            messages.error(request, "Please confirm that you want to link this application.")
            return redirect('admin_link_application')

        try:
            # ✅ Check 3: Application exists
            application = get_object_or_404(Essco_Models.ApplicationModel, id=application_id)

            # ✅ Check 4: User exists
            user = get_object_or_404(User, id=user_id)

            # ✅ Check 5: Application is not already linked
            if application.customer:
                messages.warning(
                    request,
                    f"Application {application.reference_number} is already linked to "
                    f"{application.customer.get_full_name() or application.customer.username}"
                )
                return redirect('admin_link_application')

            # ✅ Check 6: Application has valid data (not empty)
            if not application.Fname or not application.Lname:
                messages.warning(
                    request,
                    f"Application {application.reference_number} has incomplete customer data. "
                    "Please verify before linking."
                )

            # ✅ Check 7: Confirm the user matches application data
            user_email_match = user.email.lower() == application.email.lower() if application.email else False
            user_name_match = (
                user.first_name.lower() == application.Fname.lower() and
                user.last_name.lower() == application.Lname.lower()
            ) if application.Fname and application.Lname else False

            match_info = []
            if user_email_match:
                match_info.append("Email matches")
            if user_name_match:
                match_info.append("Name matches")

            # ✅ Link the application
            old_user = application.customer
            application.customer = user
            application.save()

            # ✅ Log the action
            log_action(
                request=request,
                user=request.user,
                action='LINK_APPLICATION',
                description=(
                    f"Admin {request.user.username} linked application {application.reference_number} "
                    f"to user {user.username} ({user.email}). "
                    f"Matches: {', '.join(match_info) if match_info else 'No matches found'}. "
                    f"Previous user: {old_user.username if old_user else 'None'}"
                ),
                application=application,
                loan=None,
                ip_address=request.META.get('REMOTE_ADDR')
            )

            messages.success(
                request,
                f"✅ Application {application.reference_number} linked to "
                f"{user.get_full_name() or user.username} successfully!"
            )
            if not match_info:
                messages.info(
                    request,
                    "⚠️ Note: User details didn't match the application data. "
                    "Please verify this is the correct user."
                )
            return redirect('admin_link_application')

        except Essco_Models.ApplicationModel.DoesNotExist:
            messages.error(request, "Application not found.")
        except User.DoesNotExist:
            messages.error(request, "User not found.")
        except Exception as e:
            logger.error(f"Failed to link application: {str(e)}", exc_info=True)
            messages.error(request, f"Failed to link application: {str(e)}")

    # GET - show form
    unlinked_applications = Essco_Models.ApplicationModel.objects.filter(customer__isnull=True).order_by('-created')
    linked_applications = Essco_Models.ApplicationModel.objects.filter(customer__isnull=False).order_by('-created')
    users = User.objects.filter(is_active=True).order_by('username')

    context = {
        'unlinked_applications': unlinked_applications,
        'linked_applications': linked_applications,
        'users': users,
        'total_unlinked': unlinked_applications.count(),
        'total_users': users.count(),
    }
    return render(request, 'admin_link_application.html', context)



# applications/views.py

@login_required
@officer_required
def admin_unlink_application(request):
    """
    Admin view to see all linked applications and unlink them
    """
    if request.method == 'POST':
        application_id = request.POST.get('application_id')
        confirm = request.POST.get('confirm', '')

        if not application_id:
            messages.error(request, "Please select an application to unlink.")
            return redirect('admin_unlink_applications')

        if confirm != 'yes':
            messages.error(request, "Please confirm that you want to unlink this application.")
            return redirect('admin_unlink_applications')

        try:
            application = get_object_or_404(Essco_Models.ApplicationModel, id=application_id)

            if not application.customer:
                messages.warning(request, f"Application {application.reference_number} is already unlinked.")
                return redirect('admin_unlink_applications')

            # Get the user before unlinking (for audit)
            old_user = application.customer

            # Unlink the application
            application.customer = None
            application.save()

            # Log the action
            log_action(
                request=request,
                user=request.user,
                action='UNLINK_APPLICATION',
                description=(
                    f"Admin {request.user.username} unlinked application {application.reference_number} "
                    f"from user {old_user.username if old_user else 'None'} ({old_user.email if old_user else 'N/A'})"
                ),
                application=application,
                loan=None,
                ip_address=request.META.get('REMOTE_ADDR')
            )

            messages.success(
                request,
                f"✅ Application {application.reference_number} unlinked from "
                f"{old_user.get_full_name() or old_user.username if old_user else 'unknown user'} successfully!"
            )
            return redirect('admin_unlink_applications')

        except Exception as e:
            messages.error(request, f"Failed to unlink application: {str(e)}")
            return redirect('admin_unlink_applications')

    # GET - show all linked applications
    linked_applications = Essco_Models.ApplicationModel.objects.filter(
        customer__isnull=False
    ).order_by('-created')

    context = {
        'linked_applications': linked_applications,
        'total_linked': linked_applications.count(),
    }
    return render(request, 'admin_unlink_applications.html', context)

######################################################################################################################################################

@staff_member_required
@login_required
def email_usage_dashboard(request):
    """
    Display email usage statistics for staff with paginated email logs
    """
    usage = EmailCounter.get_usage_summary()

    # Get all email logs ordered by most recent
    from applications.models import EmailLog
    all_emails = EmailLog.objects.all().order_by('-sent_at')

    # ===== PAGINATION =====
    paginator = Paginator(all_emails, 10)  # Show 20 emails per page
    page_number = request.GET.get('page', 1)

    try:
        recent_emails = paginator.page(page_number)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page
        recent_emails = paginator.page(1)
    except EmptyPage:
        # If page is out of range, deliver last page of results
        recent_emails = paginator.page(paginator.num_pages)

    context = {
        'usage': usage,
        'recent_emails': recent_emails,  # This is now a Page object
        'today': timezone.now().date(),
    }
    return render(request, 'email_usage.html', context)

