# app/routes/template_helpers.py
# Template system with auto-injection of user context and permissions.

import os
import json
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.config import TEMPLATE_DIR
from app.database import engine
from app.models import UserPermission, LabInfo
from app.services.auth_service import get_current_user


_base_templates = Jinja2Templates(directory=TEMPLATE_DIR)


class AutoUserTemplates:
    """Wrapper that auto-injects current_user, has_page(), has_button() into every template."""

    def __init__(self, base):
        self.base = base
        self.env = base.env

    def TemplateResponse(self, name, context, **kwargs):
        request = context.get("request")

        try:
            with Session(engine) as sess:
                # Resolve current_user
                if "current_user" not in context and request:
                    user = get_current_user(request, sess)
                    if user:
                        sess.expunge(user)
                        context["current_user"] = user
                    else:
                        context["current_user"] = None

                if "current_user" not in context:
                    context["current_user"] = None

                # Load permissions
                current_user = context.get("current_user")
                is_admin = current_user and (current_user.role == "admin" or current_user.username == "admin")

                user_perms = {}
                if current_user and not is_admin:
                    perms = sess.exec(
                        select(UserPermission).where(UserPermission.user_id == current_user.id)
                    ).all()
                    for p in perms:
                        buttons = []
                        if p.allowed_buttons:
                            try:
                                buttons = json.loads(p.allowed_buttons)
                            except Exception:
                                buttons = []
                        user_perms[p.page_key] = buttons

                # Inject global lab_name
                if "global_lab_name" not in context:
                    lab_info_obj = sess.exec(select(LabInfo).limit(1)).first()
                    context["global_lab_name"] = lab_info_obj.lab_name if lab_info_obj and lab_info_obj.lab_name else ""
        except Exception:
            if "current_user" not in context:
                context["current_user"] = None
            current_user = context.get("current_user")
            is_admin = current_user and (current_user.role == "admin" or current_user.username == "admin")
            user_perms = {}
            if "global_lab_name" not in context:
                context["global_lab_name"] = ""

        # Permission helpers for Jinja templates
        def has_page(page_key):
            if is_admin:
                return True
            return page_key in user_perms

        def has_button(page_key, button_key):
            if is_admin:
                return True
            if page_key not in user_perms:
                return False
            return button_key in user_perms[page_key]

        context["has_page"] = has_page
        context["has_button"] = has_button
        context["is_admin"] = is_admin
        context["user_perms"] = user_perms

        return self.base.TemplateResponse(name, context, **kwargs)


templates = AutoUserTemplates(_base_templates)
