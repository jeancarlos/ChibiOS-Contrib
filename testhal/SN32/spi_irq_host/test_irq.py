#!/usr/bin/env python3
"""Exercise the actual SN32 SPI IRQ handler with fake registers."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[3]
source = (root / 'os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c').read_text()
start = source.index('static inline void spi_lld_irq_handler(')
end = source.index('\n/*===', start)
handler = source[start:end]
prefix = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <assert.h>
#define SPI_READY 1
#define SPI_ACTIVE 2
typedef struct { unsigned RXFIFOTHIF; } RIS;
typedef struct { unsigned RXFIFOTHIC; } IC;
typedef struct { RIS RIS_b; IC IC_b; uint16_t DATA; } Registers;
typedef struct SPIDriver SPIDriver;
typedef struct { void (*data_cb)(SPIDriver *); } Config;
struct SPIDriver { Registers *spi; Config *config; uint8_t *rxbuf; const uint8_t *txbuf; size_t idx, count; int state; };
#define chSysLockFromISR() ((void)0)
#define chSysUnlockFromISR() ((void)0)
#define __spi_isr_complete_code(p) do { (p)->state = SPI_READY; if ((p)->config->data_cb) (p)->config->data_cb(p); } while (0)
'''
suffix = r'''
static int calls;
static int rearm;
static void completed(SPIDriver *d) {
    ++calls;
    if (rearm) {
        d->state = SPI_ACTIVE;
        d->idx = 0;
        d->count = 1;
        d->spi->DATA = 0x55;
    }
}
int main(int argc, char **argv) {
    (void)argv;
    Registers regs = {.RIS_b.RXFIFOTHIF = 1};
    Config cfg = {.data_cb = completed};
    SPIDriver d = {.spi=&regs, .config=&cfg, .idx=0, .count=1, .state=SPI_ACTIVE};
    if (argc == 1) {
    spi_lld_irq_handler(&d);
    assert(calls == 1);
    assert(d.state == SPI_READY);
    spi_lld_irq_handler(&d);
    assert(calls == 1); /* Tail clocks cannot complete the same transfer twice. */
    }
    calls = 0;
    rearm = 1;
    d.state = SPI_ACTIVE;
    d.idx = 0;
    d.count = 1;
    spi_lld_irq_handler(&d);
    assert(calls == 1);
    assert(d.state == SPI_ACTIVE);
    assert(regs.DATA == 0x55); /* Old callback must not write over new transfer. */
    rearm = 0;
    calls = 0;
    uint8_t tx[2] = {0x21, 0x22};
    uint8_t rx[2] = {0, 0};
    d.state = SPI_ACTIVE;
    d.idx = 0;
    d.count = 2;
    d.txbuf = tx;
    d.rxbuf = rx;
    regs.DATA = 0x31;
    spi_lld_irq_handler(&d);
    assert(rx[0] == 0x31 && regs.DATA == 0x22 && calls == 0);
    regs.DATA = 0x32;
    spi_lld_irq_handler(&d);
    assert(rx[1] == 0x32 && calls == 1 && regs.DATA == 0);
    return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.c').write_text(prefix + handler + suffix)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(path / 'test.c'), '-o', str(path / 'test')], check=True)
    results = [subprocess.run(args, check=False).returncode for args in ([str(path / 'test')], [str(path / 'test'), 'rearm'])]
    if any(results):
        raise SystemExit(1)
