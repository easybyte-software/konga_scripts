# Script di utilità comune per Konga

Questo repository contiene una serie di script Python di utilità comune per l'utilizzo con EasyByte Konga. Se non altrimenti specificato gli script possono essere eseguiti correttamente sia dal menu *Script* dall'interno di Konga (scelta consigliata) che da linea di comando.

> **Attenzione**: tutti gli script richiedono almeno la versione 1.8.0 di Konga.


## Installazione su Konga

Dopo aver scaricato il repository (con *git* o scaricando come file *zip*) lanciare Konga e dal menu *Script* scegliere *Gestisci script…*; nella finestra di gestione degli script, aggiungere la directory dove si è scaricato il repository tra i percorsi di ricerca.

Gli script contenuti in questo repository appariranno a questo punto automaticamente nel menu *Script*, all'interno del sotto-menu *Utilità*.


## Installazione da linea di comando

Assicurarsi di avere installato kongalib e Pillow:

```
pip install kongalib Pillow
```

Gli script contenuti in questo repository saranno a questo punto pronti per essere eseguiti. 


# Script contenuti

- [Script di utilità comune per Konga](#script-di-utilit%c3%a0-comune-per-konga)
  - [Installazione su Konga](#installazione-su-konga)
  - [Installazione da linea di comando](#installazione-da-linea-di-comando)
- [Script contenuti](#script-contenuti)
  - [Consolida immagini](#consolida-immagini)
  - [Consolida reparti POS](#consolida-reparti-pos)
  - [Importazione immagini](#importazione-immagini)
  - [Riposiziona immagini e allegati](#riposiziona-immagini-e-allegati)


## Consolida immagini

**Sorgente**: `consolida_immagini.py`

Permette di generare automaticamente le versioni web e miniatura (se mancanti) per tutte le immagini degli articoli contenute in un database. La generazione delle immagini dipende dall'immagine che lo script trova già presente per un articolo, secondo la seguente tabella:

Immagine trovata | Genera immagine web | Genera miniatura
---------------- | ------------------- | ----------------
Immagine normale | :heavy_check_mark: | :heavy_check_mark:
Immagine web | | :heavy_check_mark:
Miniatura | |

Alla fine della procedura verrà mostrato un riepilogo sulle immagini generate automaticamente.

---

## Consolida reparti POS

**Sorgente**: `consolida_reparti.py`

Controlla eventuali incongruenze tra le aliquote IVA degli articoli di magazzino e le aliquote IVA dei reparti POS abbinati agli stessi articoli. Il consolidamento dei dati e la conseguente risoluzione di queste possibili incongruenze dipende dalle opzioni selezionate all'avvio dello script:

* Codice dell'azienda; identifica l'azienda per cui consolidare gli articoli.
* Tipo di correzione; specifica come comportarsi in caso di incongruenza dei dati, ossia quale modifica apportare all'articolo: si può scegliere se impostare su di esso il numero di reparto in base all'aliquota IVA abbinata, oppure impostare l'aliquota IVA in base al reparto POS abbinato.
* Riporta errore per articoli senza aliquota IVA; se l'opzione è selezionata, l'operazione riporterà un errore nel log per ogni articolo senza aliquota IVA.
* Esegui simulazione; se specificata, questa opzione fa in modo che lo script simuli tutte le sue operazioni senza effettuare alcuna modifica reale al database.

Al termine dell'esecuzione dello script, verrà mostrato un log di riepilogo con le informazioni sulle operazioni effettuate (o simulate).

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
maggiore della dimensione web | :heavy_check_mark: | :heavy_check_mark: (generata) | :heavy_check_mark: (generata)
maggiore di 48 x 48 | | :heavy_check_mark: | :heavy_check_mark: (generata)
fino a 48 x48 | | | :heavy_check_mark:

Notare che la *dimensione web* è quella impostata in *configurazione azienda -> Magazzino* (valore predefinito: 240 x 320)

Alla fine della procedura verrà mostrato un riepilogo sulle immagini importate e generate automaticamente.

> **Attenzione**: per ogni articolo per cui è importata un'immagine, tutte le precedenti immagini ad esso associate (normale, web e miniatura) verranno perse.

---

## Riposiziona immagini e allegati

**Sorgente**: `riposiziona_immagini_allegati.py`

Consolida la struttura delle directory dove sono salvati allegati ed immagini del database. In particolare, questo script assicura che i file siano posizionati in sotto-cartelle gerarchiche, in modo che ogni sotto-cartella abbia al massimo 1000 file al suo interno. Sarà possibile specificare alcune opzioni all'avvio dello script:

* Codice dell'azienda; permette di specificare di quale azienda consolidare allegati e immagini.
* Consolida nomi file; se abilitato, tutti i file saranno rinominati nella forma `<CODE>_<UUID>`, dove `<CODE>` è il codice del record abbinato all'immagine o allegato, e `UUID` è un UUID univoco generato automaticamente.
* Elimina riferimenti non validi; se abilitato, tutti gli allegati e le immagini che fanno riferimento a nomi di file non validi (ovvero file non più esistenti o inaccessibili) verranno eliminati.
* Esegui simulazione; se specificata, questa opzione fa in modo che lo script simuli tutte le sue operazioni senza effettuare alcuna modifica reale al database o al filesystem.

Al termine dell'esecuzione dello script, verrà mostrato un log di riepilogo con le informazioni sulle operazioni effettuate (o simulate).
