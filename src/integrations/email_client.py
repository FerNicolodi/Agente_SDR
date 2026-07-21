"""Notificação interna por e-mail quando um lead informa horário para reunião.

Via SMTP genérico — funciona com Office 365, Gmail ou qualquer provedor que
aceite SMTP AUTH. Requer SMTP_HOST, SMTP_USER e SMTP_PASSWORD no ambiente.

Se a DB1 usa Microsoft 365 (mesmo domínio do e-mail db1.com.br), os valores
mais prováveis são SMTP_HOST=smtp.office365.com e SMTP_PORT=587, com o
próprio e-mail e senha (ou senha de aplicativo, se houver MFA) — mas isso
depende de o tenant permitir SMTP AUTH, o que precisa ser confirmado.
"""
from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText

def send_email(subject: str, body: str, to: str | None = None) -> None:
    """Levanta KeyError se alguma variável de ambiente obrigatória estiver
    ausente, ou uma exceção do smtplib se a autenticação/envio falhar. A
    rota chamadora decide o que fazer nesses casos (ver dry_run.py para um
    exemplo de fallback amigável quando o SMTP ainda não está configurado).

    MED-05: nenhum e-mail hardcoded — o destinatário padrão DEVE ser
    definido via NOTIFICATION_EMAIL_TO no ambiente. Se não estiver
    configurado e `to` não for passado, lança KeyError com mensagem clara.
    """
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    from_addr = os.environ.get("SMTP_FROM", user)
    if to:
        to_addr = to
    else:
        to_addr = os.environ.get("NOTIFICATION_EMAIL_TO", "")
        if not to_addr:
            raise KeyError(
                "NOTIFICATION_EMAIL_TO não está definido no ambiente. "
                "Configure a variável com o e-mail destino das notificações."
            )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    with smtplib.SMTP(host, port, timeout=15) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(from_addr, [to_addr], msg.as_string())
