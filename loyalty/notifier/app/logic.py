def build_text(event: dict) -> str:
    """Текст уведомления по событию «операция обработана»."""
    if event["status"] == "rejected":
        return f"Операция отклонена: {event['reject_reason']}"
    delta = event["points_delta"]
    if delta > 0 or (delta == 0 and event["type"] == "purchase"):
        return f"Начислено {delta} баллов, баланс {event['balance_after']}"
    return f"Списано {abs(delta)} баллов, баланс {event['balance_after']}"
