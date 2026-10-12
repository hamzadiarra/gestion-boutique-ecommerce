"""Vérifie le menu FR/EN dans Edge sur une base temporaire."""
import os
import tempfile
from pathlib import Path
from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from playwright.sync_api import sync_playwright, expect


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LanguageSelectorBrowserTests(StaticLiveServerTestCase):
    def test_switch_flags_current_page_and_responsive_header(self):
        admin = User.objects.create_user("language-admin", is_superuser=True)
        client = Client(); client.force_login(admin)
        session = client.session.session_key
        output = Path(tempfile.gettempdir()) / "gestion-boutique-language-selector"
        output.mkdir(exist_ok=True)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel=os.getenv("PLAYWRIGHT_CHANNEL", "msedge"), headless=True)
            try:
                for role in ("visitor", "admin"):
                    for width in (320, 390, 820, 1280, 1440):
                        context = browser.new_context(viewport={"width":width,"height":900}, service_workers="block", reduced_motion="reduce")
                        if role == "admin":
                            context.add_cookies([{"name":"sessionid","value":session,"url":self.live_server_url}])
                        page = context.new_page()
                        errors = []; page.on("pageerror", lambda err: errors.append(str(err)))
                        target = self.live_server_url + "/products/?q=test&tri=prix_asc"
                        page.goto(target, wait_until="networkidle")
                        for language in ("en", "fr"):
                            toggle = page.locator('.site-menu-toggle')
                            if toggle.is_visible():
                                toggle.click()
                                page.wait_for_timeout(400)
                            page.locator('.site-language-trigger').click()
                            menu = page.locator('.site-language-dropdown')
                            expect(menu).to_be_visible()
                            self.assertEqual(menu.locator('button[name="language"]').count(), 2)
                            for flag in menu.locator('img').all():
                                self.assertTrue(flag.evaluate('e=>e.complete && e.naturalWidth>0'))
                            clipped = menu.evaluate("""e => {
                                const box=e.getBoundingClientRect();
                                for(let p=e.parentElement;p;p=p.parentElement){
                                    const css=getComputedStyle(p),r=p.getBoundingClientRect();
                                    if(/auto|scroll|hidden|clip/.test(css.overflowY) && (box.top<r.top-1 || box.bottom>r.bottom+1))return true;
                                }
                                return false;
                            }""")
                            self.assertFalse(clipped, f"Language options clipped: {role} {width}px")
                            box=menu.bounding_box()
                            self.assertGreaterEqual(box['x'], -1)
                            self.assertLessEqual(box['x']+box['width'], width+1)
                            page.screenshot(path=str(output/f"{role}-{width}-{language}-menu.png"))
                            with page.expect_navigation():
                                menu.locator(f'button[value="{language}"]').click()
                            self.assertEqual(page.url, target)
                            expect(page.locator('html')).to_have_attribute('lang', language)
                            expect(page.locator(f'.site-language-dropdown button[value="{language}"]')).to_have_attribute('aria-current', 'true')
                            self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                            self.assertEqual(page.locator('.site-header').evaluate('e=>getComputedStyle(e).position'), 'sticky')
                            page.evaluate("scrollTo({top:500,behavior:'instant'})")
                            page.wait_for_timeout(80)
                            self.assertLessEqual(abs(page.locator('.site-header').bounding_box()['y']),1)
                            page.evaluate("scrollTo({top:0,behavior:'instant'})")
                        self.assertEqual(errors, [])
                        print(f"{role} {width}px: FR/EN, flags, current URL, sticky header OK",flush=True)
                        context.close()
            finally:
                browser.close()
