"""Visual product audit; PRODUCT_UI_PHASE=before/after/historical. Local images required."""
import json
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
from products.models import Product, Wishlist
from cart.models import Cart, CartItem

@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProductPhotoBrowserTests(StaticLiveServerTestCase):
    def test_product_photos(self):
        phase=os.getenv('PRODUCT_UI_PHASE','after')
        output=Path(tempfile.gettempdir())/'gestion-boutique-product-photos'/phase
        output.mkdir(parents=True,exist_ok=True)
        sources=sorted((Path(settings.MEDIA_ROOT)/'products').glob('*.jpg'))
        self.assertTrue(sources)
        with tempfile.TemporaryDirectory(prefix='product-photo-fixtures-') as media, override_settings(MEDIA_ROOT=media):
            user=User.objects.create_user('photos-client')
            category=Category.objects.create(nom='Collection test')
            products=[]
            for index,source in enumerate(sources):
                product=Product.objects.create(categorie=category,nom=f'Article {index} collection',prix=12500,prix_promotion=9900 if index==0 else None,stock=0 if index==2 else 8,vedette=True,description='Description du produit, conservée intégralement.')
                product.image.save(source.name,ContentFile(source.read_bytes()))
                products.append(product)
            wishlist=Wishlist.objects.create(utilisateur=user);wishlist.produits.add(*products)
            cart=Cart.objects.create(utilisateur=user)
            for product in products[:2]:
                CartItem.objects.create(panier=cart,produit=product,prix=product.prix,quantite=1)
            client=Client();client.force_login(user)
            routes=[('accueil',reverse('home')),('catalogue',reverse('product_list')),('recherche',reverse('product_list')+'?q=Article'),('categorie',reverse('category_detail',args=[category.slug])),('fiche',reverse('product_detail',args=[products[0].slug])),('favoris',reverse('wishlist')),('panier',reverse('cart_detail'))]
            report=[]
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',headless=True)
                context=browser.new_context(service_workers='block',reduced_motion='reduce')
                context.add_cookies([{'name':'sessionid','value':client.session.session_key,'url':self.live_server_url}])
                page=context.new_page()
                if phase=='historical':
                    css=subprocess.check_output(['git','show','9878a4f^:static/css/style.css'])
                    page.route('**/static/css/style.css*',lambda r:r.fulfill(body=css,content_type='text/css'))
                    page.route('**/static/css/refonte.css*',lambda r:r.fulfill(body='',content_type='text/css'))
                for width in (320,390,768,1024,1280,1920):
                    page.set_viewport_size({'width':width,'height':900})
                    for name,url in routes:
                        response=page.goto(self.live_server_url+url,wait_until='networkidle')
                        self.assertEqual(response.status,200)
                        page.locator('img[loading="lazy"]').evaluate_all("els=>els.forEach(e=>e.loading='eager')")
                        page.locator('.shop-product-media img,.shop-detail-image img,.shop-cart-image img').evaluate_all("imgs=>Promise.all(imgs.map(i=>i.decode().catch(()=>null)))")
                        page.wait_for_load_state('networkidle')
                        metrics=page.evaluate("""() => ({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,images:[...document.querySelectorAll('.shop-product-media,.shop-detail-image,.shop-cart-image')].map(e=>{const r=e.getBoundingClientRect(),i=e.querySelector('img');return {kind:e.className,width:r.width,height:r.height,loaded:!i||i.complete&&i.naturalWidth>0,fit:i?getComputedStyle(i).objectFit:null}})})""")
                        metrics['page']=name;report.append(metrics)
                        page.screenshot(path=str(output/f'{name}-{width}.png'),full_page=True)
                        if phase=='after':
                            self.assertLessEqual(metrics['scrollWidth'],width+1)
                            for image in metrics['images']:
                                self.assertTrue(image['loaded'])
                                ratio=4/5 if image['kind']=='shop-product-media' else 1
                                self.assertAlmostEqual(image['width']/image['height'],ratio,places=2)
                                if image['fit']:
                                    self.assertEqual(image['fit'],'contain')
                    print(f'{phase}: {width}px, 7 pages',flush=True)
                (output/'metrics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                browser.close()
            print(f'ARTIFACTS: {output}',flush=True)
