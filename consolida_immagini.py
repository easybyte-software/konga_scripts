# -*- title: Consolida immagini -*-
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



def load_record(record, embedded, client, log, code_azienda):
	if embedded:
		if ('Contenuto' not in record) and ('id' in record):
			record['Contenuto'] = client.select_data('EB_DatiBinari', ['Contenuto'], kongalib.OperandEQ('id', record['id']))[0][0]
		data = record.get('Contenuto', None)
	else:
		filename = os.path.basename(record.get('NomeAllegato', ''))
		if not filename:
			return
		external_path = kongautil.get_external_images_path('EB_Articoli', None if (record.get('ref_Azienda', None) is None) else code_azienda)
		if external_path is None:
			data = None
			log.error('Percorso delle immagini non accessibile; controllare la configurazione del database')
		else:
			parts = os.path.basename(filename).split('_')
			if len(parts) == 1:
				subdir = '0'
			else:
				subdir = parts[0][:-3] or '0'
			filename = os.path.join(external_path, subdir, filename)
			if not os.path.exists(filename):
				filename = os.path.join(external_path, filename)
			try:
				with open(filename, 'rb') as f:
					data = f.read()
			except:
				data = None
			record['@filename'] = filename
	if data:
		try:
			record['@image'] = Image.open(io.BytesIO(data))
		except Exception as e:
			log.error('Errore di caricamento immagine: ' + str(e))



def gen_image(source_record, dest_record, dest_size, tipo, code_articolo, embedded, id_tabella, client, log):
	dest_record['@image'] = source_record['@image'].copy()
	dest_record['@image'].thumbnail(dest_size)
	record_id = dest_record.get('id', None)
	filename = '%s_%s_%s.png' % (code_articolo, { TIPO_WEB: 'web', TIPO_MINIATURA: 'tmb' }[tipo], str(uuid.uuid5(uuid.uuid1(),'mga')))
	dest_record['NomeAllegato'] = filename
	if '@filename' in source_record:
		dirname = os.path.dirname(source_record['@filename'])
		dest_record['@filename'] = os.path.join(dirname, filename)

	if embedded:
		buffer = io.BytesIO()
		dest_record['@image'].convert('RGBA').save(buffer, 'PNG')
		dest_record['Contenuto'] = buffer.getvalue()
	else:
		try:
			with open(dest_record['@filename'], 'wb') as f:
				dest_record['@image'].convert('RGBA').save(f, 'PNG')
			os.chmod(dest_record['@filename'], 0o644)
		except Exception as e:
			log.error("Errore nel salvataggio dell'immagine '%s' (%s)" % (dest_record['@filename'], str(e)))
			return
		dest_record['Contenuto'] = None
	if record_id is None:
		dest_record.update({
			'ref_Tabella':			id_tabella,
			'Riga':					source_record['Riga'],
			'val_Tipo':				tipo,
			'NomeOriginale':		dest_record.get('@filename', ''),
			'Descrizione':			'',
			'NumeroProgressivo':	1,
			'ref_Azienda':			source_record['ref_Azienda'],
		})

	record = {}
	for key, value in dest_record.items():
		if key[0] != '@':
			record['EB_DatiBinari.%s' % key] = value
	# print record
	if record_id is None:
		client.insert_record('EB_DatiBinari', record)
		log.info("Articolo %s: generata l'immagine %s ed il record corrispondente su EB_DatiBinari" % (code_articolo, { TIPO_WEB: 'web', TIPO_MINIATURA: 'miniatura' }[tipo]))
	else:
		client.update_record('EB_DatiBinari', record, id=record_id)
		log.info("Articolo %s: generata l'immagine %s ed aggiornato il record esistente su EB_DatiBinari" % (code_articolo, { TIPO_WEB: 'web', TIPO_MINIATURA: 'miniatura' }[tipo]))



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
	updated_arts = []
	added_web = 0
	added_thumb = 0
	kongaui.open_progress('Consolidamento immagini in corso...')
	client.begin_transaction()
	try:
		embed_images = (client.select_data('EB_Master', ['EB_Master.val_ImagesStorageType'])[0][0] == 1)
		id_azienda, web_width, web_height = client.select_data('EB_StatoArchivi', ['EB_StatoArchivi.ref_Azienda', 'EB_StatoArchivi.LarghezzaImgWeb', 'EB_StatoArchivi.AltezzaImgWeb'], kongalib.OperandEQ('EB_StatoArchivi.ref_Azienda.Codice', params['code_azienda']))[0]
		id_tabella = client.select_data('EB_Tabelle', ['EB_Tabelle.id'], kongalib.OperandEQ('EB_Tabelle.Nome', 'EB_Articoli'))[0][0]

		records = {}
		results = client.select_data_as_dict('EB_DatiBinari', ['id', 'Riga', 'val_Tipo', 'NomeAllegato', 'ref_Azienda'], kongalib.AND(kongalib.OperandIN('val_Tipo', (TIPO_NORMALE, TIPO_WEB, TIPO_MINIATURA)), kongalib.OperandEQ('ref_Tabella', id_tabella), kongalib.OR(kongalib.OperandIsNull('ref_Azienda'), kongalib.OperandEQ('ref_Azienda', id_azienda))))
		for record in results:
			image_row = record['Riga']
			image_type = record['val_Tipo']

			if image_row not in records:
				records[image_row] = { TIPO_NORMALE: {}, TIPO_MINIATURA: {}, TIPO_WEB: {} }
			if not records[image_row][image_type]:
				records[image_row][image_type] = record

		index = 0
		for image_row, image_data in records.items():
			kongaui.set_progress((index * 100.0) / len(records), None, 'Immagini per articolo %d di %d' % (index+1, len(records)))
			if kongaui.is_progress_aborted():
				break

			code_articolo = client.select_data('EB_Articoli', ['Codice'], kongalib.OperandEQ('id', image_row))[0][0]
			record_full = image_data[TIPO_NORMALE]
			record_web = image_data[TIPO_WEB]
			record_thumb = image_data[TIPO_MINIATURA]

			load_record(record_full, embed_images, client, log, params['code_azienda'])
			load_record(record_web, embed_images, client, log, params['code_azienda'])
			load_record(record_thumb, embed_images, client, log, params['code_azienda'])
			updated = False

			if (record_full.get('@image', None) is not None) and (record_web.get('@image', None) is None):
				gen_image(record_full, record_web, (web_width, web_height), TIPO_WEB, code_articolo, embed_images, id_tabella, client, log)
				updated = True
				added_web += 1

			if (record_web.get('@image', None) is not None) and (record_thumb.get('@image', None) is None):
				gen_image(record_web, record_thumb, (48, 48), TIPO_MINIATURA, code_articolo, embed_images, id_tabella, client, log)
				updated = True
				added_thumb += 1

			record_full.clear()
			record_web.clear()
			record_thumb.clear()

			if updated:
				updated_arts.append(image_row)
			index += 1

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
			kongautil.notify_data_changes('EB_Articoli', updated_arts)
			kongautil.notify_data_changes('EB_Articoli')
			kongautil.print_log(log, "Esito consolidamento immagini")



main()

