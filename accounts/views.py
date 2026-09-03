from django.shortcuts import render, redirect
from django.contrib.auth.views import LoginView
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse, reverse_lazy
from django.conf import settings
from django.contrib.auth import logout, login
import logging
import geocoder
from audit.services import log_action
from applications.models import ApplicationModel

# ✅ FIX THESE IMPORTS
from . import forms as Essco_Forms
from .forms import SetPasswordForm, EmailRegistrationForm  # ← ADD THIS
from applications.emails import send_registration_link

User = get_user_model()
logger = logging.getLogger(__name__)

# Create your views here.

from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy
from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponseRedirect
import geocoder
import logging

logger = logging.getLogger(__name__)

class CustomLoginView(LoginView):
    template_name = "accounts/login.html"

    def get(self, request, *args, **kwargs):
        """Clear rate limit counter on GET (new login attempt)"""
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        """
        Handle successful login with rate limiting check AND session fixation protection.
        """
        # ⭐ Rate limiting: Check if user has too many failed attempts
        username = form.cleaned_data.get('username')
        ip = self.get_client_ip(self.request)

        # Use both username and IP for rate limiting
        cache_key = f"login_attempts_{username}_{ip}"
        attempts = cache.get(cache_key, 0)

        # ⭐ Check if rate limit exceeded
        if attempts >= 5:  # 5 failed attempts per hour
            messages.error(
                self.request,
                "Too many failed login attempts. Please try again later or reset your password."
            )
            logger.warning(
                f"RATE LIMIT EXCEEDED: Username={username}, IP={ip}, Attempts={attempts}"
            )
            return self.render_to_response(self.get_context_data(form=form))

        # ✅ Clear rate limit on successful login
        cache.delete(cache_key)

        # ============================================================
        # ⭐ SESSION FIXATION PROTECTION - CRITICAL!
        # ============================================================
        # Regenerate session ID BEFORE login to prevent session fixation
        # This ensures the attacker's old session ID is invalidated
        self.request.session.cycle_key()  # 🛡️ Creates NEW session ID

        # ⭐ Log the successful login (before super() call)
        print("FORM VALID CALLED")
        user = form.get_user()

        # Get IP address
        ip = self.get_client_ip(self.request)

        # Geo lookup (basic)
        try:
            g = geocoder.ip(ip)
            country = g.country if g.ok else "Unknown"
            city = g.city if g.ok else "Unknown"
        except Exception as e:
            logger.warning(f"Geo lookup failed: {e}")
            country = "Unknown"
            city = "Unknown"

        # Log the successful login
        log_action(
            request=self.request,
            user=user,
            action="LOGIN",
            ip_address=ip,
            description=(
                f"{user.username} ({user.role}) "
                f"Logged in from {city}, {country}. "
                f"IP: {ip}"
            )
        )

        # ============================================================
        # ⭐ COMPLETE LOGIN
        # ============================================================
        # Now call super() which will complete the login process
        # The session ID has already been regenerated above
        response = super().form_valid(form)

        # ⭐ Clear rate limit on successful login (again, just to be safe)
        cache.delete(cache_key)

        return response

    def form_invalid(self, form):
        """
        Handle failed login with rate limiting.
        """
        username = form.cleaned_data.get('username', 'unknown')
        ip = self.get_client_ip(self.request)

        # ⭐ Rate limiting: Increment failed attempts
        cache_key = f"login_attempts_{username}_{ip}"
        attempts = cache.get(cache_key, 0)
        attempts += 1
        cache.set(cache_key, attempts, 3600)  # 1 hour expiry

        # ⭐ Log the failed attempt
        logger.warning(
            f"FAILED LOGIN ATTEMPT: Username={username}, IP={ip}, Attempt={attempts}/5"
        )

        # ⭐ Show warning when approaching limit
        if attempts >= 4:
            messages.warning(
                self.request,
                f"You have {5 - attempts} attempt(s) remaining before your account is temporarily locked."
            )

        if attempts >= 5:
            messages.error(
                self.request,
                "Too many failed login attempts. Please try again later or reset your password."
            )
            logger.warning(
                f"RATE LIMIT EXCEEDED: Username={username}, IP={ip}, Attempts={attempts}"
            )

        return super().form_invalid(form)

    def get_success_url(self):
        """
        Redirect based on user role.
        """
        user = self.request.user

        if user.role == "customer":
            return reverse_lazy("Essco_Cover")
        elif user.role in ["officer", "manager", "admin"]:
            return reverse_lazy("admin_dashboard")

        return reverse_lazy("home")

    def get_client_ip(self, request):
        """
        Get client IP address, handling proxies.
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip






class CustomLoginView1(LoginView):
    template_name = "accounts/login.html"

    def form_valid(self, form):
        print("FORM VALID CALLED")
        response = super().form_valid(form)
        user = self.request.user
        ip = (self.request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0] or self.request.META.get("REMOTE_ADDR"))

        # Geo lookup (basic)
        g = geocoder.ip(ip)

        country = g.country if g.ok else "Unknown"
        city = g.city if g.ok else "Unknown"

        log_action(request=self.request, user=self.request.user,  action="LOGIN", ip_address=ip,
        description=(
                        f"{user.username} ({user.role}) "
                        f"Logged in from {city}, {country}. "
                        f"IP: {ip}"
                    ))

        return response

    def get_success_url(self):
        user = self.request.user

        if user.role == "customer":
            return reverse_lazy("Essco_Cover")
        elif user.role == "officer":
            return reverse_lazy("admin_dashboard")
        elif user.role == "manager":
            return reverse_lazy("admin_dashboard")
        elif user.role == "admin":
            return reverse_lazy("admin_dashboard")


        return reverse_lazy("home")

def logout_user(request):
    if request.user.is_authenticated:
        ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0] or request.META.get("REMOTE_ADDR"))

        g = geocoder.ip(ip)

        country = g.country if g.ok else "Unknown"
        city = g.city if g.ok else "Unknown"

        log_action(request=request,  user=request.user,  action="LOGOUT", ip_address=ip,
            description=(
                f"{request.user.username} ({request.user.role}) "
                f"Logged out from {city}, {country}. "
                f"IP: {ip}"
            ),
        )

    logout(request)

    return redirect("login")


def Essco_Cover(request):
    context = {'is_admin': request.user.is_staff, 'is_superuser': request.user.is_superuser,}
    return render(request, 'accounts/index.html', context)

def Finance_Application_Cover(request):
    context = {'is_admin': request.user.is_staff, 'is_superuser': request.user.is_superuser,}
    return render(request, 'Finance_Application_Form.html', context)

def Unauthorized(request):
    return render(request, 'accounts/Unathorized.html')


############################################################################################################################################################
##################################################################     REGISTER      #######################################################################
############################################################################################################################################################

def register(request):
    """
    Registration page - only allows users who have submitted an application

    Flow:
    1. Check if email has a loan application
    2. If yes, check if user account exists
    3. If exists → Send password reset link
    4. If not exists → Create user and send registration link
    """
    if request.user.is_authenticated:
        return redirect('Essco_Cover')

    # ⭐ Rate limiting: Get client IP
    ip = get_client_ip(request)
    cache_key = f"register_attempts_{ip}"
    attempts = cache.get(cache_key, 0)

    if request.method == 'POST':
        # ⭐ Rate limit: 5 registration attempts per hour per IP
        if attempts >= 5:  # 5 attempts per hour
            messages.error(
                request,
                "Too many registration attempts from this IP. Please try again later."
            )
            logger.warning(f"RATE LIMIT EXCEEDED: Registration attempts from IP {ip} ({attempts})")
            form = Essco_Forms.EmailRegistrationForm()
            return render(request, 'accounts/register.html', {'form': form})

        form = Essco_Forms.EmailRegistrationForm(request.POST)

        if form.is_valid():
            email = form.cleaned_data['email'].lower().strip()

            # ⭐ Log the attempt
            logger.info(f"REGISTRATION ATTEMPT: Email={email}, IP={ip}, Attempt={attempts+1}/5")

            # =============================================================
            # STEP 1: Check if email exists in Applications
            # =============================================================
            if not ApplicationModel.objects.filter(email=email).exists():
                messages.error(
                    request,
                    '❌ No loan application found with this email address. '
                    'Please apply for a loan first before creating an account.'
                )
                # ⭐ Don't increment rate limit on invalid email - they might be trying
                return render(request, 'accounts/register.html', {'form': form})

            # ⭐ Increment rate limit counter (only for valid emails)
            cache.set(cache_key, attempts + 1, 3600)  # 1 hour expiry

            # =============================================================
            # STEP 2: Check if user account already exists
            # =============================================================
            user_exists = User.objects.filter(email=email).exists()

            if user_exists:
                # ✅ Existing user - send password reset link
                user = User.objects.get(email=email)

                if user.role != 'customer':
                    messages.error(request, 'This email is not registered as a customer.')
                    return render(request, 'accounts/register.html', {'form': form})

                # Generate password reset link
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                set_password_url = request.build_absolute_uri(
                    reverse('set_password', kwargs={'uidb64': uid, 'token': token})
                )

                if send_registration_link(email, set_password_url, is_new_user=False):
                    messages.success(
                        request,
                        f'✅ Password reset link sent to {email}. Please check your email.'
                    )
                    # ⭐ Clear rate limit on success
                    cache.delete(cache_key)
                    return redirect('registration_sent')
                else:
                    messages.error(request, '❌ Failed to send email. Please try again.')

            else:
                # ✅ New user - create account and send registration link
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=None,
                    role='customer',
                    is_active=False
                )

                # Generate registration link
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                set_password_url = request.build_absolute_uri(
                    reverse('set_password', kwargs={'uidb64': uid, 'token': token})
                )

                if send_registration_link(email, set_password_url, is_new_user=True):
                    messages.success(
                        request,
                        f'✅ Registration link sent to {email}. Please check your email to continue.'
                    )
                    # ⭐ Clear rate limit on success
                    cache.delete(cache_key)
                    return redirect('registration_sent')
                else:
                    messages.error(request, '❌ Failed to send email. Please try again.')

    else:
        # GET request - reset rate limit (optional)
        # This prevents frustration for legitimate users
        # If you want to track GET requests too, remove this line
        # cache.delete(cache_key)
        form = Essco_Forms.EmailRegistrationForm()

    context = {
        'form': form,
        'attempts_remaining': max(0, 5 - attempts) if request.method == 'POST' else 5,
        'show_warning': attempts >= 3,
    }
    return render(request, 'accounts/register.html', context)

def get_client_ip(request):
    """
    Get client IP address, handling proxies.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip






def register1(request):
    """
    Registration page - only allows users who have submitted an application

    Flow:
    1. Check if email has a loan application
    2. If yes, check if user account exists
    3. If exists → Send password reset link
    4. If not exists → Create user and send registration link
    """
    if request.user.is_authenticated:
        return redirect('Essco_Cover')

    if request.method == 'POST':
        form = Essco_Forms.EmailRegistrationForm(request.POST)

        if form.is_valid():
            email = form.cleaned_data['email'].lower().strip()

            # =============================================================
            # STEP 1: Check if email exists in Applications
            # =============================================================
            if not ApplicationModel.objects.filter(email=email).exists():
                messages.error(
                    request,
                    '❌ No loan application found with this email address. '
                    'Please apply for a loan first before creating an account.'
                )
                return render(request, 'accounts/register.html', {'form': form})

            # =============================================================
            # STEP 2: Check if user account already exists
            # =============================================================
            user_exists = User.objects.filter(email=email).exists()

            if user_exists:
                # ✅ Existing user - send password reset link
                user = User.objects.get(email=email)

                if user.role != 'customer':
                    messages.error(request, 'This email is not registered as a customer.')
                    return render(request, 'accounts/register.html', {'form': form})

                # Generate password reset link
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                set_password_url = request.build_absolute_uri(
                    reverse('set_password', kwargs={'uidb64': uid, 'token': token})
                )

                if send_registration_link(email, set_password_url, is_new_user=False):
                    messages.success(
                        request,
                        f'✅ Password reset link sent to {email}. Please check your email.'
                    )
                    return redirect('registration_sent')
                else:
                    messages.error(request, '❌ Failed to send email. Please try again.')

            else:
                # ✅ New user - create account and send registration link
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=None,
                    role='customer',
                    is_active=False
                )

                # Generate registration link
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                set_password_url = request.build_absolute_uri(
                    reverse('set_password', kwargs={'uidb64': uid, 'token': token})
                )

                if send_registration_link(email, set_password_url, is_new_user=True):
                    messages.success(
                        request,
                        f'✅ Registration link sent to {email}. Please check your email to continue.'
                    )
                    return redirect('registration_sent')
                else:
                    messages.error(request, '❌ Failed to send email. Please try again.')

    else:
        form = Essco_Forms.EmailRegistrationForm()

    return render(request, 'accounts/register.html', {'form': form})





def registerdebug(request):
    """
    Registration page - only allows users who have submitted an application
    """
    print("=" * 60)
    print("🔵 REGISTER VIEW STARTED")
    print(f"📝 Request method: {request.method}")
    print(f"👤 User authenticated: {request.user.is_authenticated}")

    if request.user.is_authenticated:
        print("⚠️ User already logged in, redirecting...")
        return redirect('Essco_Cover')

    if request.method == 'POST':
        print("📨 POST request received")
        form = Essco_Forms.EmailRegistrationForm(request.POST)

        if form.is_valid():
            email = form.cleaned_data['email'].lower().strip()
            print(f"📧 Valid email: {email}")

            # =============================================================
            # STEP 1: Check if this email exists in Applications
            # =============================================================
            print("🔍 STEP 1: Checking Application table...")
            application_exists = ApplicationModel.objects.filter(email=email).exists()
            print(f"  Application exists: {application_exists}")

            if not application_exists:
                print("❌ No application found - blocking registration")
                messages.error(
                    request,
                    '❌ No loan application found with this email address. '
                    'Please apply for a loan first before creating an account.'
                )
                return render(request, 'accounts/register.html', {'form': form})

            # =============================================================
            # STEP 2: Check if user account already exists
            # =============================================================
            print("🔍 STEP 2: Checking User table...")
            user_exists = User.objects.filter(email=email).exists()
            print(f"  User exists: {user_exists}")

            if user_exists:
                print("🔄 CASE A: User already exists - sending password reset")
                user = User.objects.get(email=email)
                print(f"  User role: '{user.role}'")
                print(f"  User is_active: {user.is_active}")

                # Check if user is a customer
                if user.role != 'customer':
                    print(f"❌ User role is '{user.role}', not 'customer'")
                    messages.error(request, 'This email is not registered as a customer.')
                    return render(request, 'accounts/register.html', {'form': form})

                print("✅ User is a customer, generating reset token...")

                # Generate password reset link
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                set_password_url = request.build_absolute_uri(
                    reverse('set_password', kwargs={'uidb64': uid, 'token': token})
                )
                print(f"🔗 Reset URL generated: {set_password_url[:50]}...")

                print("📤 Attempting to send email...")
                try:
                    result = send_registration_link(email, set_password_url, is_new_user=False)
                    print(f"  send_registration_link returned: {result}")

                    if result:
                        print("✅ Email sent successfully!")
                        messages.success(
                            request,
                            f'✅ Password reset link sent to {email}. Please check your email.'
                        )
                        return redirect('registration_sent')
                    else:
                        print("❌ send_registration_link returned False")
                        messages.error(request, '❌ Failed to send email. Please try again.')

                except Exception as e:
                    print(f"❌ Exception in email sending: {e}")
                    import traceback
                    print(traceback.format_exc())
                    logger.error(f"Failed to send reset email: {e}")
                    messages.error(request, '❌ Failed to send email. Please try again.')

            else:
                print("🆕 CASE B: New user - creating account and sending registration link")
                # ... rest of new user logic
                pass

    else:
        print("📄 GET request - displaying empty form")
        form = Essco_Forms.EmailRegistrationForm()

    print("=" * 60)
    return render(request, 'accounts/register.html', {'form': form})

def register1(request):
    """Registration page - checks if email exists and stops if it does"""

    if request.user.is_authenticated:
        return redirect('Essco_Cover')

    if request.method == 'POST':
        form = Essco_Forms.EmailRegistrationForm(request.POST)

        if form.is_valid():
            email = form.cleaned_data['email']

            # =============================================================
            # CHECK: Does this email already exist?
            # =============================================================
            if User.objects.filter(email=email).exists():
                # ✅ Stop here - user already exists
                messages.success(request, 'If this email is registered, you will receive a link to access your account.')
                return render(request, 'accounts/register.html', {'form': form})

            # =============================================================
            # NEW USER - Create account and send link
            # =============================================================
            user = User.objects.create_user(
                username=email,
                email=email,
                password=None,
                role='customer',
                is_active=False
            )

            # Generate token and link
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            set_password_url = request.build_absolute_uri(
                reverse('set_password', kwargs={'uidb64': uid, 'token': token})
            )

            # Send email
            try:
                send_registration_link(email, set_password_url, is_new_user=True)

                messages.success(
                    request,
                    f'✅ We\'ve sent a registration link to {email}. Please check your email to continue.'
                )
                return redirect('registration_sent')

            except Exception as e:
                logger.error(f"Failed to send email: {e}")
                messages.error(request, '❌ Failed to send email. Please try again.')

    else:
        form = Essco_Forms.EmailRegistrationForm()

    return render(request, 'accounts/register.html', {'form': form})


def set_password(request, uidb64, token):
    """
    Set password page - user clicks link from email
    URL: /accounts/set-password/<uidb64>/<token>/

    This view handles:
    1. Verifying the token is valid
    2. Setting the new password
    3. Activating the user account
    4. Logging the user in
    5. Redirecting to appropriate page
    """
    # =============================================================
    # STEP 1: Decode and verify user
    # =============================================================
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    # =============================================================
    # STEP 2: Check if token is valid
    # =============================================================
    if user is not None and default_token_generator.check_token(user, token):

        # =============================================================
        # STEP 3: Handle POST (form submission)
        # =============================================================
        if request.method == 'POST':
            form = Essco_Forms.SetPasswordForm(user, request.POST)

            if form.is_valid():
                # ✅ Save the new password (this calls user.set_password())
                form.save()

                # ✅ Activate the user account
                user.is_active = True
                user.save()

                # ✅ Log the user in
                login(request, user)

                logger.info(f"✅ Password set and user logged in: {user.email}")
                messages.success(
                    request,
                    '✅ Password set successfully! You are now logged in.'
                )

                # ✅ Check if there's product data in session (from application flow)
                if 'product_data' in request.session:
                    return redirect('apply')
                else:
                    # Redirect to customer dashboard
                    return redirect('customer_dashboard')
            else:
                # Form has errors - show them
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f'{field}: {error}')

        else:
            # ✅ GET request - display empty form
            form = Essco_Forms.SetPasswordForm(user)

        # Render the set password page with form
        return render(request, 'accounts/set_password.html', {
            'form': form,
            'user': user,
            'valid_token': True,
        })

    else:
        # =============================================================
        # STEP 4: Invalid or expired token
        # =============================================================
        logger.warning(f"Invalid or expired token attempt for uidb64: {uidb64}")
        messages.error(
            request,
            '❌ The link is invalid or has expired. Please request a new one.'
        )
        return redirect('register')

def registration_sent(request):
    """
    Show confirmation that email was sent
    """
    return render(request, 'accounts/registration_sent.html')