"""Edge visual checks on isolated Django data. CATEGORY_UI_PHASE=before/after/historical."""
import json
from concurrent.futures import ThreadPoolExecutor
import os
import subprocess
import tempfile
from pathlib import Path
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.files.base import ContentFile
from django.test import Client, override_settings
from django.urls import reverse
from playwright.sync_api import sync_playwright
from categories.models import Category
from products.models import Product

WIDTHS = (320, 390, 768, 1024, 1280, 1920)

@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CategoryAvatarBrowserTests(StaticLiveServerTestCase):
    def test_category_and_avatar_layouts(self):
        phase = os.getenv("CATEGORY_UI_PHASE", "after")
        output = Path(tempfile.gettempdir()) / "gestion-boutique-category-avatars" / phase
        output.mkdir(parents=True, exist_ok=True)
        original_media = Path(settings.MEDIA_ROOT)
        photos = sorted((original_media / "categories").glob("*.jpg"))[:5]
        portrait = next((original_media / "profiles").glob("photo_*.jpg"), None)
        self.assertTrue(photos, "Local category photos required for visual comparison")
        self.assertIsNotNone(portrait, "Local portrait required for visual comparison")
        with tempfile.TemporaryDirectory(prefix="category-avatar-fixtures-") as media, override_settings(MEDIA_ROOT=media):
            categories = []
            for index, name in enumerate(("Mode et accessoires", "Chaussures", "Maison", "Collections", "Nos incontournables", "Sans photographie")):
                category = Category.objects.create(nom=name)
                if index < len(photos):
                    category.image.save(f"category-{index}.jpg", ContentFile(photos[index].read_bytes()))
                Product.objects.create(categorie=category, nom=f"Article {index}", prix=12500, stock=4)
                categories.append(category)
            users, sessions = {}, {}
            for role in ("client", "admin", "vendeur", "livreur"):
                user = User.objects.create_user("visuel-" + role, first_name="Compte", last_name="Visuel")
                user.profile.role = role
                user.profile.photo.save("portrait.jpg", ContentFile(portrait.read_bytes()))
                user.profile.save()
                users[role] = user
                client = Client(); client.force_login(user)
                sessions[role] = client.session.session_key
            routes = [("categories", "client", reverse("category_list")),
                ("categorie", "client", reverse("category_detail", args=[categories[0].slug])),
                ("profil", "client", reverse("profile")),
                ("profil-edition", "client", reverse("profile_edit")),
                ("vendeurs", "admin", reverse("admin_vendeurs_performance")),
                ("vendeur", "admin", reverse("admin_vendeur_performance_detail", args=[users["vendeur"].profile.pk])),
                ("espace-vendeur", "vendeur", reverse("vendeur_dashboard")),
                ("espace-livreur", "livreur", reverse("livreur_dashboard"))]
            if phase == "historical":
                routes = routes[:2]
            results, defects = [], []
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="msedge", headless=True)
                context = browser.new_context(service_workers="block", reduced_motion="reduce")
                page = context.new_page()
                if phase == "historical":
                    old_css = subprocess.check_output(["git", "show", "9878a4f^:static/css/style.css"])
                    page.route("**/static/css/style.css*", lambda route: route.fulfill(body=old_css, content_type="text/css"))
                    page.route("**/static/css/refonte.css*", lambda route: route.fulfill(body="", content_type="text/css"))
                for width in WIDTHS:
                    page.set_viewport_size({"width": width, "height": 900})
                    for name, role, route in routes:
                        context.clear_cookies()
                        context.add_cookies([{"name":"sessionid", "value":sessions[role], "url":self.live_server_url}])
                        response = page.goto(self.live_server_url + route, wait_until="networkidle")
                        page.locator('img[loading="lazy"]').evaluate_all("els=>els.forEach(e=>e.loading='eager')")
                        page.wait_for_load_state("networkidle")
                        metrics = page.evaluate("""() => {
                            const selectors=['.shop-category-tile','.shop-category-hero > div:first-child','.site-avatar','.account-avatar','.dashboard-avatar'];
                            const boxes=selectors.flatMap(selector=>[...document.querySelectorAll(selector)].filter(e=>e.getClientRects().length).map(e=>{
                                const r=e.getBoundingClientRect(),img=e.querySelector('img'),s=img?getComputedStyle(img):null;
                                return {selector,width:r.width,height:r.height,loaded:img?img.complete&&img.naturalWidth>0:true,fit:s?.objectFit};
                            }));
                            return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,boxes};
                        }""")
                        metrics.update(page=name,status=response.status)
                        page.screenshot(path=str(output / f"{name}-{width}.png"), full_page=True)
                        page.evaluate("scrollTo({top:500,behavior:'instant'})")
                        metrics['stickyTop']=page.locator('.site-header').evaluate('e=>e.getBoundingClientRect().top')
                        if width < 1200:
                            page.evaluate("scrollTo({top:0,behavior:'instant'})")
                            page.locator('.site-menu-toggle').click(); page.wait_for_timeout(350)
                            metrics['mobileMenu']=page.locator('#navbarMenu').is_visible()
                            metrics['menuOverflow']=page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                            page.screenshot(path=str(output / f"{name}-menu-{width}.png"))
                        results.append(metrics)
                        invalid_avatar=any(abs(b['width']-b['height'])>1 for b in metrics['boxes'] if 'avatar' in b['selector'])
                        if phase == 'after':
                            for box in metrics['boxes']:
                                if box['selector'] in ('.shop-category-tile', '.shop-category-hero > div:first-child'):
                                    self.assertAlmostEqual(box['width'] / box['height'], 4 / 3, places=2)
                        if response.status != 200 or metrics['scrollWidth']>width+1 or invalid_avatar or any(not b['loaded'] for b in metrics['boxes']) or abs(metrics['stickyTop'])>1 or metrics.get('menuOverflow') or metrics.get('mobileMenu') is False:
                            defects.append(metrics)
                    print(f"{phase} {width}px: {len(routes)} pages", flush=True)
                # Navigation category -> products, profile -> edit, and absent-photo fallbacks.
                context.clear_cookies()
                context.add_cookies([{"name":"sessionid","value":sessions['client'],"url":self.live_server_url}])
                page.goto(self.live_server_url+reverse('category_list'))
                page.locator('.shop-category-tile[href="'+reverse('category_detail', args=[categories[0].slug])+'"]').click()
                self.assertEqual(page.url, self.live_server_url+reverse('category_detail', args=[categories[0].slug]))
                def clear_test_photos():
                    from accounts.models import Profile
                    from django.db import connection
                    try:
                        Profile.objects.filter(utilisateur_id__in=[u.pk for u in users.values()]).update(photo='')
                    finally:
                        connection.close()
                with ThreadPoolExecutor(max_workers=1) as executor:
                    executor.submit(clear_test_photos).result()
                page.goto(self.live_server_url+reverse('profile'))
                page.locator('a[href="'+reverse('profile_edit')+'"]').first.click()
                self.assertEqual(page.url, self.live_server_url+reverse('profile_edit'))
                for name, role, route in routes:
                    context.clear_cookies()
                    context.add_cookies([{"name":"sessionid","value":sessions[role],"url":self.live_server_url}])
                    self.assertEqual(page.goto(self.live_server_url+route).status,200)
                    if name in ('profil','vendeur'):
                        page.screenshot(path=str(output / f"{name}-fallback.png"),full_page=True)
                (output / "metrics.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
                (output / "defects.json").write_text(json.dumps(defects,indent=2),encoding="utf-8")
                print(f"ARTIFACTS: {output}; DEFECTS: {len(defects)}",flush=True)
                if phase == 'after':
                    self.assertEqual(defects,[])
                browser.close()
