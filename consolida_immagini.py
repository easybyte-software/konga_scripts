# -*- title: Utilità / Consolida immagini -*-
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



def main():
	params = kongaui.execute_form([ {
				'name': 'code_azienda',
				'label': "Codice azienda",
				'type': 'company_code',
			} ],
			"Consolida immagini",
			"Questo script consolida le immagini di tutti gli articoli comuni e aziendali di un database, in modo da generare automaticamente le versioni web e miniatura a partire dall'immagine normale.",
			condition = "code_azienda")
	if not params:
		return

	log = kongalib.Log()
	client = kongautil.connect()
	added_web = 0
	added_thumb = 0
	kongaui.open_progress('Consolidamento immagini in corso...')
	client.begin_transaction()
	try:
		web_width, web_height = client.select_data('EB_StatoArchivi', ['EB_StatoArchivi.LarghezzaImgWeb', 'EB_StatoArchivi.AltezzaImgWeb'], kongalib.OperandEQ('EB_StatoArchivi.ref_Azienda.Codice', params['code_azienda']))[0]

		results = client.select_data('EB_Articoli', ['EB_Articoli.id', 'EB_Articoli.Codice'], kongalib.OR(kongalib.OperandEQ('EB_Articoli.ref_Azienda.Codice', params['code_azienda']), kongalib.OperandIsNull('EB_Articoli.ref_Azienda')))
		for index, (id_art, code_art) in enumerate(results):
			kongaui.set_progress((index * 100.0) / len(results), None, 'Immagini per articolo %d di %d' % (index+1, len(results)))
			if kongaui.is_progress_aborted():
				break

			try:
				normal_data, _dummy, normal_filename, _dummy = client.fetch_binary('EB_Articoli', id_art, TIPO_NORMALE)
			except:
				normal_data = normal_filename = None
			try:
				web_data, _dummy, web_filename, _dummy = client.fetch_binary('EB_Articoli', id_art, TIPO_WEB)
			except:
				web_data = web_filename = None
			try:
				thumb_data, _dummy, thumb_filename, _dummy = client.fetch_binary('EB_Articoli', id_art, TIPO_MINIATURA)
			except:
				thumb_data = thumb_filename = None

			if normal_data and (web_data is None):
				bitmap = Image.open(io.BytesIO(normal_data))
				bitmap.thumbnail((web_width, web_height))
				buffer = io.BytesIO()
				bitmap.convert('RGBA').save(buffer, 'PNG')
				web_data = buffer.getvalue()
				web_filename = normal_filename
				try:
					client.store_binary('EB_Articoli', id_art, TIPO_WEB, data=web_data, original_filename=web_filename, code_azienda=params['code_azienda'])
				except Exception as e:
					log.error("Articolo %s: errore di salvataggio dell'immagine web: %s" % (code_art, str(e)))
				else:
					log.info("Articolo %s: generata l'immagine web" % code_art)
					added_web += 1

			if web_data and (thumb_data is None):
				bitmap = Image.open(io.BytesIO(web_data))
				bitmap.thumbnail((48, 48))
				temp = Image.new('RGBA', (48, 48))
				temp.paste(bitmap, ((48 - bitmap.size[0]) // 2, (48 - bitmap.size[1]) // 2))
				buffer = io.BytesIO()
				temp.save(buffer, 'PNG')
				thumb_data = buffer.getvalue()
				thumb_filename = web_filename
				try:
					client.store_binary('EB_Articoli', id_art, TIPO_MINIATURA, data=thumb_data, original_filename=thumb_filename, code_azienda=params['code_azienda'])
				except Exception as e:
					log.error("Articolo %s: errore di salvataggio della miniatura: %s" % (code_art, str(e)))
				else:
					log.info("Articolo %s: generata l'immagine miniatura" % code_art)
					added_thumb += 1

	finally:
		if kongaui.is_progress_aborted():
			client.rollback_transaction()
			kongaui.close_progress()
		else:
			log.info("Aggiunte %d immagini web e %d miniature" % (added_web, added_thumb))
			if log.has_errors():
				client.rollback_transaction()
			else:
				client.commit_transaction()
			kongaui.close_progress()
			kongautil.notify_data_changes('EB_Articoli')
			kongautil.print_log(log, "Esito consolidamento immagini")



main()

