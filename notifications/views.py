from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import Notification
from django.contrib import messages
from django.core.paginator import Paginator


@login_required
def notification_list(request):
    notifications = Paginator(request.user.notifications.all(), 10).get_page(request.GET.get("page"))

    return render(
        request,
        "notifications/notification_list.html",
        {
            "page_obj": notifications,
        }
    )


@login_required
def mark_as_read(request, notification_id):
    if request.method != "POST":
        messages.info(request, "Cette action doit être confirmée depuis le centre de notifications.")
        return redirect("notification_list")
    notification = get_object_or_404(
        Notification,
        id=notification_id,
        utilisateur=request.user
    )
    notification.lu = True
    notification.save()

    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect("notification_list")


@login_required
def mark_all_as_read(request):
    if request.method != "POST":
        messages.info(request, "Cette action doit être confirmée depuis le centre de notifications.")
        return redirect("notification_list")
    request.user.notifications.filter(lu=False).update(lu=True)
    messages.success(request, "Toutes les notifications ont été marquées comme lues.")

    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect("notification_list")
