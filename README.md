# Script di utilità comune per Konga

Questo repository contiene una serie di script Python di utilità comune per l'utilizzo con EasyByte Konga. Se non altrimenti specificato gli script possono essere eseguiti correttamente sia dal menu *Script* dall'interno di Konga (scelta consigliata) che da linea di comando.


## Installazione su Konga

> **Attenzione**: gli script richiedono almeno la versione 1.8.0 di Konga.

Dopo aver scaricato il repository (con *git* o scaricando come file *zip*) lanciare Konga e dal menu *Script* scegliere *Gestisci script…*; nella finestra di gestione degli script, aggiungere la directory dove si è scaricato il repository tra i percorsi di ricerca.

Gli script contenuti in questo repository appariranno a questo punto automaticamente nel menu *Script*.


## Installazione da linea di comando

Assicurarsi di avere installato kongalib e Pillow:

```
pip install kongalib Pillow
```

> **Attenzione**: gli script richiedono almeno la versione 1.8.0 di kongalib

Gli script contenuti in questo repository saranno a questo punto pronti per essere eseguiti. 


# Script contenuti

## Consolida immagini

**Sorgente**: `consolida_immagini.py`

Permette di generare automaticamente le versioni web e miniatura (se mancanti) per tutte le immagini degli articoli contenute in un database. La generazione delle immagini dipende dall'immagine che lo script trova già presente per un articolo, secondo la seguente tabella:

Immagine trovata | Genera immagine web | Genera miniatura
---------------- | ------------------- | ----------------
Immagine normale | <ul><li>[x] &nbsp;</li></ul> | <ul><li>[x] &nbsp;</li></ul>
Immagine web | <ul><li>[ ] &nbsp;</li></ul> | <ul><li>[x] &nbsp;</li></ul>
Miniatura | <ul><li>[ ] &nbsp;</li></ul> | <ul><li>[ ] &nbsp;</li></ul>

Alla fine della procedura verrà mostrato un riepilogo sulle immagini generate automaticamente.

---

## Importazione immagini

**Sorgente**: `importa_immagini.py`

Permette di importare nuove immagini per gli articoli di un database, a partire dai file contenuti in una cartella specifica. Per funzionare correttamente, la procedura richiede che i nomi dei file corrispondano ad uno tra **codice**,  **codice alternativo**, **barcode** o **codice articolo fornitore** degli articoli già presenti sul database.

All'avvio verranno richiesti alcuni parametri:

* Codice dell'azienda; congiuntamente al tipo di codice articolo, questo verrà usato per ricercare gli articoli a cui associare le immagini all'interno del database.
* Tipo di codice articolo; il nome del singolo file immagine dovrà essere uguale al corrispondente codice sull'articolo su cui si vuole importare l'immagine.
* Percorso da cui importare le immagini.

La ricerca di un articolo corrispondente ad un file immagine cercherà prima all'interno degli articoli dell'azienda specificata, dopodichè cercherà tra gli articoli comuni.

Dipendentemente dalla dimensione iniziale dell'immagine, verranno anche generate le immagini web e miniatura, secondo la seguente tabella:

Dimensione immagine | Immagine normale | Immagine web | Miniatura
------------------- | ---------------- | ------------ | ---------
maggiore della dimensione web | <ul><li>[x] &nbsp;</li></ul> | <ul><li>[x] (generata)</li></ul> | <ul><li>[x] (generata)</li></ul>
maggiore di 48 x 48 | <ul><li>[ ] &nbsp;</li></ul> | <ul><li>[x] &nbsp;</li></ul> | <ul><li>[x] (generata)</li></ul>
fino a 48 x48 | <ul><li>[ ] &nbsp;</li></ul> | <ul><li>[ ] &nbsp;</li></ul> | <ul><li>[x] &nbsp;</li></ul>

Notare che la *dimensione web* è quella impostata in *configurazione azienda -> Magazzino* (valore predefinito: 240 x 320)

Alla fine della procedura verrà mostrato un riepilogo sulle immagini importate e generate automaticamente.

> **Attenzione**: per ogni articolo per cui è importata un'immagine, tutte le precedenti immagini ad esso associate (normale, web e miniatura) verranno perse.
