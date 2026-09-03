from django.urls import path
from django.contrib.auth import views as auth_views
from . import views as esscofinance

urlpatterns = [
    #path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("login/", esscofinance.CustomLoginView.as_view(), name="login"),
    path("logout/", esscofinance.logout_user, name="logout"),
    path("register/", esscofinance.register, name="register"),
    path('registration-sent/', esscofinance.registration_sent, name='registration_sent'),
    path('set-password/<uidb64>/<token>/', esscofinance.set_password, name='set_password'),
    # THE Cover pages for the differnt users
    path("", esscofinance.Essco_Cover, name="Essco_Cover"),
    # The Unauthorized page
    path('Unauthorized/', esscofinance.Unauthorized, name="Unauthorized"),

]