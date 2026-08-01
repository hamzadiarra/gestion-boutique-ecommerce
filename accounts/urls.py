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
        "profile/change-password/",
        views.change_password,
        name="change_password"
    ),
]