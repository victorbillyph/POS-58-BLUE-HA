# MPT-II Bluetooth Printer para Home Assistant

Integração (custom component/HACS) para impressoras térmicas de 58mm tipo **MPT-II / MPT-11 / GOOJPRT** que falam **ESC/POS**.

Expõe dois serviços no Home Assistant:

- `mpt_printer.print_text` — imprime um texto com formatação (alinhamento, negrito, tamanho, corte).
- `mpt_printer.print_raw` — envia bytes ESC/POS brutos em base64.

## Instalação via HACS

1. Publique este repositório no GitHub.
2. No HACS: **⋮ → Repositórios personalizados → Categoria: Integração** e aponte para a URL do repo.
3. Instale "MPT-II Bluetooth Printer" pelo HACS.
4. Reinicie o Home Assistant.

Instalação manual (alternativa):

```bash
cp -r custom_components/mpt_printer <diretorio_config_do_ha>/custom_components/
```

## Configuração

**Configurar Dispositivos e Serviços → Adicionar Integração → MPT-II Bluetooth Printer.**

Dois modos de conexão:

### 1. Bluetooth BLE (recomendado)

Funciona se o host do Home Assistant tem adaptador Bluetooth e o HA enxerga a impressora
(o nome precisa conter `MPT`, `print`, `pos` ou `thermal` para aparecer na lista).

- Se a impressora for detectada, ela aparece automaticamente em **Dispositivos e Serviços**.
- Ou adicione manualmente escolhendo na lista de dispositivos encontrados / digitando o MAC.

> Dica: pareie/confie a impressora no host (`bluetoothctl pair`/`trust`) mas **não mantenha conexão ativa** — a integração conecta sozinha a cada trabalho.

### 2. Serial (`/dev/rfcomm0`) — para variantes só SPP (Bluetooth clássico)

Se a impressora não aparecer como BLE, ela provavelmente é Bluetooth clássico SPP.
No host que roda o HA (precisa ter acesso ao BlueZ, ex.: instalação não-container ou container com `/var/run/dbus` e net raw):

```bash
bluetoothctl
  power on
  agent on
  default-agent
  scan on          # anote o MAC da MPT-II
  pair XX:XX:XX:XX:XX:XX
  trust XX:XX:XX:XX:XX:XX
  quit

sudo rfcomm bind 0 XX:XX:XX:XX:XX:XX 1   # cria /dev/rfcomm0 persistente até reboot
```

Depois configure a integração com **Serial device** apontando para `/dev/rfcomm0`.

## Uso

Ações (Developer Tools → Actions / automações):

```yaml
# Texto simples
action: mpt_printer.print_text
data:
  message: |
        *** CUPOM NAO FISCAL ***
        Pedido #123
        2x Cafe ......... R$ 8,00
        Total ........... R$ 8,00
        Obrigado, volte sempre!

# Centralizado + grande + cortar papel
action: mpt_printer.print_text
data:
  message: "ABERTURA DE CAIXA"
  align: center
  size: double
  bold: true
  feed: 4
  cut: true

# Com data/hora
action: mpt_printer.print_text
data:
  message: >
    Teste {{ now().strftime('%d/%m/%Y %H:%M') }}
```

Opções por impressora (Configurar → MPT-II → ⚙): largura do papel em caracteres
(32 para 58mm), alinhamento/tamanho/avanço/corte padrão.

## CLI standalone (debug fora do HA)

```bash
pip install bleak
python3 tools/bluetooth_print.py --ble AA:BB:CC:DD:EE:FF --center "Ola"
python3 tools/bluetooth_print.py --serial /dev/rfcomm0 "Ola"
```

## Solução de problemas

| Problema | Solução |
| --- | --- |
| Não aparece na descoberta | Nome não bate com os filtros; use MAC manual. Confirme com `bluetoothctl devices`. |
| `cannot_connect` | Impressora dorme após inatividade — desligue/ligue, aproxime. |
| Caracteres estranhos em acentos | A integração codifica em CP437; evite emojis/símbolos fora desse conjunto. |
| Saída truncada no fim | Aumente `feed`; alguns firmwares descartam os últimos bytes sem avanço de papel. |
| Corte não funciona | Mini impressoras manuais geralmente não têm lâmina — deixe `cut: false`. |

## Notas técnicas

- Comando ESC/POS: init `\x1b@`, alinhamento `\x1ba`, negrito `\x1bE`, tamanho `\x1d!`,
  avanço `\x1bd`, corte parcial `\x1dV\x42\x00`.
- BLE: escreve na característica `0000ff02` (serviço `0000ff00`), caindo para qualquer característica
  gravável; chunks de 20 bytes com intervalo de 20ms (limite dos firmwares antigos).
