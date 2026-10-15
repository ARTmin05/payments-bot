"""Минимальный клиент Crypto Pay API (Crypto Bot): создание счёта и проверка статуса."""

import aiohttp

MAINNET = "https://pay.crypt.bot/api"
TESTNET = "https://testnet-pay.crypt.bot/api"  # тестовая сеть — ненастоящие деньги, для отладки


class CryptoPayError(Exception):
    pass


class CryptoPay:
    def __init__(self, token: str, testnet: bool = True):
        self.base = TESTNET if testnet else MAINNET
        self.headers = {"Crypto-Pay-API-Token": token}

    async def _call(self, method: str, **params):
        async with aiohttp.ClientSession(headers=self.headers) as s:
            async with s.post(f"{self.base}/{method}", json=params, timeout=aiohttp.ClientTimeout(total=20)) as r:
                data = await r.json(content_type=None)
        if not data.get("ok"):
            raise CryptoPayError(str(data.get("error")))
        return data["result"]

    async def create_invoice(self, amount: str, description: str, payload: str, expires_in: int) -> dict:
        return await self._call("createInvoice", asset="USDT", amount=amount, description=description,
                                payload=payload, expires_in=expires_in)

    async def get_statuses(self, invoice_ids: list[str]) -> dict[str, str]:
        """{invoice_id: 'active' | 'paid' | 'expired'}"""
        if not invoice_ids:
            return {}
        result = await self._call("getInvoices", invoice_ids=",".join(invoice_ids))
        return {str(inv["invoice_id"]): inv["status"] for inv in result.get("items", [])}

    @staticmethod
    def pay_url(invoice: dict) -> str:
        return invoice.get("bot_invoice_url") or invoice.get("pay_url")
