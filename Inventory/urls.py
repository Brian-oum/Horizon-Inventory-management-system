from django.contrib import admin
from django.urls import path,include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('invent.urls')),

    # Password Reset URLs
    # Step 1: Form to request password reset email
    path('password_reset/',
         auth_views.PasswordResetView.as_view(template_name='invent/password_reset_form.html'),
         name='password_reset'),

    # Step 2: Confirmation that email has been sent
    path('password_reset/done/',
         auth_views.PasswordResetDoneView.as_view(template_name='invent/password_reset_done.html'),
         name='password_reset_done'),

    # Step 3: Link in email to set new password (with token)
    path('reset/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(template_name='invent/password_reset_confirm.html'),
         name='password_reset_confirm'),

    # Step 4: Confirmation that password has been reset
    path('reset/done/',
         auth_views.PasswordResetCompleteView.as_view(template_name='invent/password_reset_complete.html'),
         name='password_reset_complete'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)