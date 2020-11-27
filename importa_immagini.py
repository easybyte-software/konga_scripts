# -*- title: Utilità / Importazione immagini -*-
# -*- konga-version-min: 1.9.0-beta -*-
# -*- requires: Pillow -*-
# -*- py3k-safe -*-
# -*- coding: utf-8 -*-

import re
import os
import os.path
import uuid
import shutil
import tempfile
import io

import kongalib
import kongautil
import kongaui

from PIL import Image


TIPO_NORMALE	= 1
TIPO_WEB		= 2
TIPO_MINIATURA	= 3


CODE_FIELD_INFO = [
	( 'EB_Articoli.Codice',						'codice' ),
	( 'EB_Articoli.CodiceAlternativo',			'codice alternativo' ),
	( 'EB_Articoli.Barcode',					'barcode' ),
	( 'EB_Articoli.CodiceArticoloFornitore',	'codice articolo fornitore' ),
]


FORM_FIELDS = [
	{
		'name': 'code_azienda',
		'label': "Codice azienda di destinazione",
		'type': 'company_code',
	},
	{
		'name': 'fieldname',
		'label': "Il nome file corrisponde al campo",
		'type': 'choice',
		'items': [ info[1].capitalize() for info in CODE_FIELD_INFO ],
		'default': 0,
	},
	{
		'name': 'path',
		'label': "Percorso sorgente",
		'type': 'dir',
	}
]



def main():
	params = kongaui.execute_form(FORM_FIELDS,
			"Importazione immagini",
			"Questo script importa tutte le immagini presenti in una cartella, qualora ad un nome file corrisponda il codice di un articolo. Le versioni web e miniatura verranno generate automaticamente dall'immagine normale.",
			condition = "path and code_azienda")
	if not params:
		return
	fieldname, fieldname_label = CODE_FIELD_INFO[params['fieldname']]

	log = kongalib.Log()
	client = kongautil.connect()
	kongaui.open_progress('Importazione immagini in corso...')

	def store(filename, type, data, code, id_art, code_art):
		try:
			client.store_binary('EB_Articoli', id_art, type, original_filename=filename, data=data, code_azienda=params['code_azienda'])
			if data is None:
				name = {
					TIPO_NORMALE: 'normale',
					TIPO_WEB: 'web',
					TIPO_MINIATURA: 'miniatura'
				}[type]
				if fieldname == 'EB_Articoli.Codice':
					log.info("Cancellata l'immagine %s dall'articolo con codice %s" % (name, code_art))
				else:
					log.info("Cancellata l'immagine %s dall'articolo con codice %s e %s %s" % (name, code_art, fieldname_label, code))
			else:
				if fieldname == 'EB_Articoli.Codice':
					log.info("Assegnata l'immagine \"%s\" all'articolo con codice %s" % (filename, code_art))
				else:
					log.info("Assegnata l'immagine \"%s\" all'articolo con codice %s e %s %s" % (filename, code_art, fieldname_label, code))
		except Exception as e:
			if data:
				if fieldname == 'EB_Articoli.Codice':
					log.error("Errore di assegnazione dell'immagine \"%s\" all'articolo con codice %s: %s" % (filename, code_art, str(e)))
				else:
					log.error("Errore di assegnazione dell'immagine \"%s\" all'articolo con codice %s e %s %s: %s" % (filename, code_art, fieldname_label, code, str(e)))
				raise

	client.begin_transaction()
	try:
		web_width, web_height = client.select_data('EB_StatoArchivi', ['EB_StatoArchivi.LarghezzaImgWeb', 'EB_StatoArchivi.AltezzaImgWeb'], kongalib.OperandEQ('EB_StatoArchivi.ref_Azienda.Codice', params['code_azienda']))[0]
		
		files = os.listdir(params['path'])
		num_files = len(files)
		for index, name in enumerate(files):
			filename = os.path.join(params['path'], name)
			code, original_ext = os.path.splitext(name)
			if kongaui.is_progress_aborted():
				break
			kongaui.set_progress((index * 100.0) / num_files, None, '%s (%d di %d)' % (name, index+1, num_files))

			if code:
				results = client.select_data('EB_Articoli', ['EB_Articoli.id', 'EB_Articoli.Codice'], kongalib.AND(kongalib.OperandEQ(fieldname, code), kongalib.OR(kongalib.OperandEQ('EB_Articoli.ref_Azienda.Codice', params['code_azienda']), kongalib.OperandIsNull('EB_Articoli.ref_Azienda'))))
				if len(results) > 1:
					codes = [ result[1] for result in results ]
					log.warning(u"Il %s %s è associato a più di un articolo! (codici %s) L'immagine non verrà associata a nessun articolo" % (fieldname_label, code, ', '.join(codes)))
					continue

				if len(results) > 0:
					id_art, code_art = results[0]
					try:
						with open(filename, 'rb') as f:
							data = f.read()
						bitmap = Image.open(io.BytesIO(data))
					except Exception as e:
						log.error('Errore di caricamento immagine da file "%s": %s' % (filename, str(e)))
						continue
					size = bitmap.size

					if (size[0] > web_width) or (size[1] > web_height):
						web_filename = None
						thumb_filename = None
					else:
						if (size[0] > 48) or (size[1] > 48):
							log.warning("L'immagine \"%s\" ha dimensioni inferiori a quelle impostate per le immagini web (%dx%d) pertanto verrà importata come immagine di tipo web (l'articolo non avrà un'immagine di tipo normale)" % (filename, web_width, web_height))
							web_filename = filename
							thumb_filename = None
						else:
							log.warning("L'immagine \"%s\" ha dimensioni inferiori alla dimensione delle miniature (48x48) pertanto verrà importata come immagine di tipo miniatura (l'articolo non avrà un'immagine di tipo normale nè una di tipo web)" % filename)
							web_filename = None
							thumb_filename = filename

					if (size[0] > web_width) or (size[1] > web_height):
						normal_data = data
						temp = bitmap.copy()
						temp.thumbnail((web_width, web_height))
						buffer = io.BytesIO()
						temp.convert('RGBA').save(buffer, 'PNG')
						data = buffer.getvalue()
						size = temp.size
					else:
						normal_data = None

					if (size[0] > 48) or (size[1] > 48):
						web_data = data
						bitmap.thumbnail((48, 48))
						temp = Image.new('RGBA', (48, 48))
						temp.paste(bitmap, ((48 - bitmap.size[0]) // 2, (48 - bitmap.size[1]) // 2))
						buffer = io.BytesIO()
						temp.save(buffer, 'PNG')
						data = buffer.getvalue()
					else:
						web_data = None

					thumb_data = data

					store(filename, TIPO_NORMALE, normal_data, code, id_art, code_art)
					store(web_filename, TIPO_WEB, web_data, code, id_art, code_art)
					store(thumb_filename, TIPO_MINIATURA, thumb_data, code, id_art, code_art)

	finally:
		if kongaui.is_progress_aborted():
			client.rollback_transaction()
			kongaui.close_progress()
		else:
			client.commit_transaction()
			kongaui.close_progress()
			kongautil.notify_data_changes('EB_Articoli')
			kongautil.print_log(log, "Esito importazione immagini")



main()

