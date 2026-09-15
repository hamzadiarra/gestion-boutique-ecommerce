from django.contrib.auth import views as auth_views
from django.urls import path

from . import views


urlpatterns = [

    path(
        "register/",
        views.register,
        name="register"
    ),


    path(
        "login/",
        views.login_view,
        name="login"
    ),


    path(
        "logout/",
        views.logout_view,
        name="logout"
    ),

    path(
        "profile/",
        views.profile_view,
        name="profile"
    ),

    path(
        "profile/edit/",
        views.profile_edit,
        name="profile_edit"
    ),

    path(
        "profile/photo/delete/",
        views.delete_profile_photo,
        name="delete_profile_photo"
    ),

    path(
        "profile/change-password/",
        views.change_password,
        name="change_password"
    ),

    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
            email_template_name="registration/password_reset_email.html",
            subject_template_name="registration/password_reset_subject.txt",
            success_url="/accounts/password-reset/done/",
        ),
        name="password_reset",
    ),

    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html"
        ),
        name="password_reset_done",
    ),

    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url="/accounts/reset/done/",
        ),
        name="password_reset_confirm",
    ),

    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]
