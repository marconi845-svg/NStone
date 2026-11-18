# Procedura avvio multifilo — post fermo lungo

Macchina: Multifilo NStone · Profilo: avvio sicuro dopo fermo > 4 ore.

## Prerequisiti

- Operatore abilitato livello 2+
- Area macchina sgombra; DPI: occhiali, guanti, scarpe antinfortunistiche
- Verificare assenza allarmi attivi sul pannello (codici E01–E99 a zero)

## Sequenza avvio (checklist)

1. **Energia e aria:** quadro generale ON, pressione aria ≥ 6 bar, valvole pneumatiche aperte
2. **Refill vasca:** livello acqua-abrasivo tra MIN e MAX; temperatura vasca < 35 °C
3. **Tensione filo:** impostare 22 kN (±1 kN) per filo Ø 7,3 mm standard — NON avviare sopra 24 kN
4. **Homing assi:** eseguire `HOME ALL` da HMI; attendere fine ciclo (~90 s)
5. **Test jog:** muovere asse Y ±50 mm a velocità 10%; verificare assenza vibrazioni anomale
6. **Avvio taglio prova:** programma `PRG_TEST_100mm.nc` su offcut; velocità avanzamento 0,8 m/min
7. **Produzione:** solo dopo pezzo prova conforme (parallelismo ±0,5 mm / 300 mm)

## Dopo fermo notturno (> 12 h)

- Svuotare e ricaricare vasca se temperatura < 10 °C (rischio gelo/additivo)
- Ispezionare guide lineari: assenza corrosione o depositi calcarea
- Controllare usura filo: sostituire se diametro < 7,0 mm misurato

## Allarmi frequenti all'avvio

| Codice | Causa | Azione |
|--------|-------|--------|
| E12 | Tensione filo bassa | Verificare pinza, raddrizzare filo |
| E23 | Livello vasca basso | Refill fino a MAX |
| E41 | Home non eseguito | Ripetere homing assi |

## Stop di emergenza

Premere E-STOP rosso → attendere arresto completo → reset solo con chiave supervisore.
Non riavviare entro 60 s dal reset E-STOP senza ispezione visiva vasca e filo.
