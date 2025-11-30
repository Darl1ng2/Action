import requests
import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup


# ============================
# Telegram 配置
# ============================
TELEGRAM_TOKEN = "7935670307:AAHAS098oMSyrwhHnxyJTJ-Osw1bfggtIvM"
TELEGRAM_CHAT_ID = "1316387556"


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
        print("✅ Telegram 推送成功" if resp.status_code == 200 else "❌ Telegram 推送失败")
    except Exception as e:
        print("❌ Telegram API 错误：", e)


# ============================
# Binance 获取价格
# ============================
def get_binance_price(paytype=None):
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }

    payload = {
        "page": 1,
        "rows": 20,
        "asset": "USDT",
        "tradeType": "BUY",   # 你买 USDT，对方卖
        "fiat": "CNY"
    }

    if paytype:
        payload["payTypes"] = [paytype]  # ALIPAY / WECHAT / BANK

    try:
        resp = requests.post(
            "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search",
            headers=headers,
            data=json.dumps(payload)
        )
        data = resp.json()

        if not data["data"]:
            return None, None

        adv = data["data"][0]
        return float(adv["adv"]["price"]), adv["advertiser"]["nickName"]

    except Exception as e:
        print("❌ Binance 获取失败:", e)
        return None, None


# ============================
# OKX 获取价格（含支付宝过滤）
# ============================
def get_okx_price(need_alipay=False):
    url = "https://www.okx.com/v3/c2c/tradingOrders/books"

    params = {
        "quoteCurrency": "CNY",
        "baseCurrency": "USDT",
        "side": "sell",          # 对方卖，你买
        "paymentMethod": "all",
        "userType": "all"
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Referer": "https://www.okx.com/c2c",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    try:
        resp = requests.get(url, params=params, headers=headers)
        data = resp.json()

        if str(data.get("code")) not in ["0", ""]:
            print("❌ OKX 请求错误:", data)
            return None, None

        orders = data["data"].get("sell", [])
        if not orders:
            return None, None

        # -------------------------
        # ⭐ 支付宝过滤逻辑（关键修复）
        # -------------------------
        if need_alipay:
            filtered = []
            for order in orders:
                methods = [m.lower() for m in order.get("paymentMethods", [])]
                # OKX 有 aliPay, alipay, AliPay 等写法，全部统一 lower 后等于 alipay
                if "alipay" in methods:
                    filtered.append(order)
            orders = filtered

        if not orders:
            return None, None

        order = orders[0]
        return float(order["price"]), order["nickName"]

    except Exception as e:
        print("❌ OKX 获取失败:", e)
        return None, None


# ============================
# HTX（火币） 获取价格
# ============================
def get_htx_price():
    URL = "https://www.htx.com/en-us/fiat-crypto/c2c-brand/buy-usdt-cny/"

    # 设置无头浏览器
    opts = Options()
    opts.add_argument("--headless")  # 无头浏览器
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=opts)

    driver.get(URL)
    time.sleep(5)

    # 关闭可能出现的弹窗
    try:
        close_button = driver.find_element(By.CSS_SELECTOR, "div[class*='close'], button[class*='close'], .ivu-modal-close")
        close_button.click()
        print("HTX 弹窗已关闭")
    except:
        pass

    # 解析网页内容
    html = driver.page_source
    soup = BeautifulSoup(html, "lxml")

    offers = []

    # 获取所有交易信息
    rows = soup.select("div.trade-list-in")

    for row in rows:
        price_tag = row.select_one(".col.price div")
        stock_tag = row.select_one(".stock")
        limit_tags = row.select(".limit span")
        payments = row.select(".payment-icon .new-block")

        if not price_tag:
            continue

        # 解析价格（例如 7.10 CNY）
        price_text = price_tag.get_text(strip=True)
        price_value = float(price_text.replace("CNY", "").strip())

        # 解析可用数量 USDT
        stock_value = None
        if stock_tag:
            stock_value = float(stock_tag.get_text(strip=True).replace("USDT", "").strip())

        # 解析限额区间
        min_limit, max_limit = None, None
        if len(limit_tags) >= 2:
            min_limit = float(limit_tags[0].get_text(strip=True).replace(",", ""))
            max_limit = float(limit_tags[1].get_text(strip=True).replace("CNY", "").replace(",", "").strip())

        # 支付方式
        payment_methods = [p.get_text(strip=True) for p in payments]

        offer = {
            "price": price_value,
            "amount_usdt": stock_value,
            "min_limit": min_limit,
            "max_limit": max_limit,
            "payment": payment_methods
        }

        offers.append(offer)

    driver.quit()
    return offers


# ============================
# 只运行一次的主逻辑
# ============================
def main():
    # 获取各平台数据
    b_price, b_seller = get_binance_price()
    b_ali_price, b_ali_seller = get_binance_price("ALIPAY")

    o_price, o_seller = get_okx_price()
    o_ali_price, o_ali_seller = get_okx_price(need_alipay=True)

    htx_offers = get_htx_price()

    # 分组：最低价格和支付宝最低价格
    msg = "📊 **USDT C2C 监控（含支付宝）**\n\n"

    # Binance
    msg += "🟡 **Binance**\n"
    msg += f"• 最低价：{b_price} RMB（{b_seller}）\n" if b_price else "• 最低价：无商家\n"
    msg += f"• 支付宝：{b_ali_price} RMB（{b_ali_seller}）\n\n" if b_ali_price else "• 支付宝：无\n\n"

    # OKX
    msg += "🔵 **OKX**\n"
    msg += f"• 最低价：{o_price} RMB（{o_seller}）\n" if o_price else "• 最低价：无商家\n"
    msg += f"• 支付宝：{o_ali_price} RMB（{o_ali_seller}）\n\n" if o_ali_price else "• 支付宝：无\n\n"

    # HTX (火币)
    msg += "🟢 **HTX**\n"
    if htx_offers:
        lowest_htx = min(htx_offers, key=lambda x: x["price"])
        lowest_ali_htx = min([o for o in htx_offers if "Alipay" in o["payment"]], key=lambda x: x["price"], default=None)
        msg += f"• 最低价：{lowest_htx['price']} RMB\n" if lowest_htx else "• 最低价：无商家\n"
        msg += f"• 支付宝：{lowest_ali_htx['price']} RMB\n\n" if lowest_ali_htx else "• 支付宝：无商家\n\n"
    else:
        msg += "• 获取失败\n"

    msg += f"⏰ 时间：{time.strftime('%Y-%m-%d %H:%M:%S')}"

    send_telegram_message(msg)

    print("已推送，结束执行。\n")


if __name__ == "__main__":
    main()
