"""Run against an explicitly started local test instance, creating synthetic data."""
import argparse
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument('--base-url',default='http://127.0.0.1:8000')
parser.add_argument('--browser-path',default=None)
parser.add_argument('--output',default='test-results')
args=parser.parse_args()
out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=args.browser_path,headless=True)
    page=browser.new_page(viewport={'width':390,'height':844},locale='ru-RU')
    for route in ['/','/register','/login']:
        page.goto(args.base_url+route)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),route
    page.goto(args.base_url+'/register')
    name='smoke_'+str(time.time_ns())[-15:]
    page.locator('#login').fill(name)
    page.locator('#email').fill(name+'@example.test')
    page.locator('#phone').fill('+79991234567')
    page.locator('#password').fill('Smoke_Test_2026!')
    page.get_by_role('button',name='Создать аккаунт').click()
    page.wait_for_url('**/login')
    page.locator('#login').fill(name)
    page.locator('#password').fill('Smoke_Test_2026!')
    page.get_by_role('button',name='Войти в аккаунт').click()
    page.wait_for_url('**/applications')
    page.goto(args.base_url+'/applications/new')
    choices=page.locator('#event option[value]:not([value=""])')
    assert choices.count(),'The test instance needs a future event'
    page.locator('#event').select_option(choices.first.get_attribute('value'))
    page.locator('#room').select_option('online')
    page.locator('#payment').select_option('card')
    page.get_by_role('button',name='Отправить заявку').click()
    page.wait_for_url('**/applications')
    assert page.locator('.application-card').count()==1
    page.screenshot(path=str(out/'application-mobile.png'),full_page=True)
    for route in ['/applications','/applications/new','/account']:
        page.goto(args.base_url+route)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),route
    page.goto(args.base_url+'/admin')
    assert 'Нет доступа' in page.locator('h1').inner_text()
    page.emulate_media(reduced_motion='reduce')
    assert page.locator('main').evaluate('e=>getComputedStyle(e).animationName')=='none'
    browser.close()
print('PASS: registration, login, application, ownership boundary, mobile layout, reduced motion')
