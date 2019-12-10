# -*- title: Importazione immagini -*-
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
	updated_arts = []
	kongaui.open_progress('Importazione immagini in corso...')
	client.begin_transaction()
	try:
		embed_images, order_images = tuple(client.select_data('EB_Master', ['EB_Master.val_ImagesStorageType', 'EB_Master.val_OrderExternalData'])[0])
		id_azienda, web_width, web_height = client.select_data('EB_StatoArchivi', ['EB_StatoArchivi.ref_Azienda', 'EB_StatoArchivi.LarghezzaImgWeb', 'EB_StatoArchivi.AltezzaImgWeb'], kongalib.OperandEQ('EB_StatoArchivi.ref_Azienda.Codice', params['code_azienda']))[0]
		id_tabella = client.select_data('EB_Tabelle', ['EB_Tabelle.id'], kongalib.OperandEQ('EB_Tabelle.Nome', 'EB_Articoli'))[0][0]

		files = os.listdir(params['path'])
		num_files = len(files)
		for index, name in enumerate(files):
			filename = original_filename = os.path.join(params['path'], name)
			code, original_ext = os.path.splitext(name)
			if kongaui.is_progress_aborted():
				break
			kongaui.set_progress((index * 100.0) / num_files, None, '%s (%d di %d)' % (name, index+1, num_files))

			if code:
				results = client.select_data('EB_Articoli', ['EB_Articoli.id', 'EB_Articoli.Codice', 'EB_Articoli.ref_Azienda'], kongalib.AND(kongalib.OperandEQ(fieldname, code), kongalib.OR(kongalib.OperandEQ('EB_Articoli.ref_Azienda', id_azienda), kongalib.OperandIsNull('EB_Articoli.ref_Azienda'))))
				if len(results) > 1:
					codes = [ result[1] for result in results ]
					log.warning(u"Il %s %s è associato a più di un articolo! (codici %s) L'immagine non verrà associata a nessun articolo" % (fieldname_label, code, ', '.join(codes)))
					continue

				if len(results) > 0:
					id_art, code_art, ref_Azienda = results[0]
					try:
						with open(filename, 'rb') as f:
							data = f.read()
						bitmap = Image.open(io.BytesIO(data))
					except Exception as e:
						log.error('Errore di caricamento immagine da file "%s": %s' % (filename, str(e)))
						continue
					size = bitmap.size

					name = code_art + '_' + str(uuid.uuid5(uuid.uuid1(),'mga'))
					web_name = code_art + '_web_' + str(uuid.uuid5(uuid.uuid1(),'mga'))
					thumb_name = code_art + '_tmb_' + str(uuid.uuid5(uuid.uuid1(),'mga')) + '.png'

					client.query("DELETE FROM EB_DatiBinari WHERE ref_Tabella = %d AND Riga = %d AND val_Tipo IN (1,2,3)" % (id_tabella, id_art))

					record = {
						'EB_DatiBinari.ref_Tabella':		id_tabella,
						'EB_DatiBinari.Riga':				id_art,
						'EB_DatiBinari.NomeOriginale':		filename,
						'EB_DatiBinari.Descrizione':		'',
						'EB_DatiBinari.NumeroProgressivo':	1,
						'EB_DatiBinari.ref_Azienda':		ref_Azienda,
					}

					subdir = code_art[:-3] or '0'
					external_path = os.path.join(kongautil.get_external_images_path('EB_Articoli', None if (ref_Azienda is None) else params['code_azienda']))
					if order_images:
						external_path = os.path.join(external_path, subdir)
					if not os.path.exists(external_path):
						os.makedirs(external_path)
						os.chmod(dest_dir, 0o2777)
					to_delete = []

					if (size[0] > web_width) or (size[1] > web_height):
						name += original_ext
						record['EB_DatiBinari.val_Tipo'] = TIPO_NORMALE
						record['EB_DatiBinari.NomeAllegato'] = name
						if embed_images:
							record['EB_DatiBinari.Contenuto'] = data
						else:
							shutil.copy(filename, os.path.join(external_path, name))
						client.insert_record('EB_DatiBinari', record)
						temp = bitmap.copy()
						temp.thumbnail((web_width, web_height))
						buffer = io.BytesIO()
						temp.convert('RGBA').save(buffer, 'PNG')
						data = buffer.getvalue()
						if not embed_images:
							with tempfile.NamedTemporaryFile(delete=False) as f:
								f.write(data)
								filename = f.name
						web_name += '.png'
						move_file = True
					else:
						log.warning("L'immagine \"%s\" ha dimensioni inferiori a quelle impostate per le immagini web (%dx%d) pertanto verrà importata come immagine di tipo web (l'articolo non avrà un'immagine di tipo normale)" % (original_filename, web_width, web_height))
						web_name += original_ext
						move_file = False

					record['EB_DatiBinari.val_Tipo'] = TIPO_WEB
					record['EB_DatiBinari.NomeAllegato'] = web_name
					if embed_images:
						record['EB_DatiBinari.Contenuto'] = data
					else:
						if move_file:
							shutil.copy(filename, os.path.join(external_path, web_name))
							os.unlink(filename)
						else:
							shutil.copy(filename, os.path.join(external_path, web_name))
					client.insert_record('EB_DatiBinari', record)

					bitmap.thumbnail((48, 48))
					thumb = Image.new('RGBA', (48, 48))
					thumb.paste(bitmap, ((48 - bitmap.size[0]) // 2, (48 - bitmap.size[1]) // 2))
					buffer = io.BytesIO()
					thumb.save(buffer, 'PNG')
					data = buffer.getvalue()
					if not embed_images:
						with tempfile.NamedTemporaryFile(delete=False) as f:
							f.write(data)
							filename = f.name
					record['EB_DatiBinari.val_Tipo'] = TIPO_MINIATURA
					record['EB_DatiBinari.NomeAllegato'] = thumb_name
					if embed_images:
						record['EB_DatiBinari.Contenuto'] = data
					else:
						shutil.copy(filename, os.path.join(external_path, thumb_name))
						os.unlink(filename)
					client.insert_record('EB_DatiBinari', record)

					updated_arts.append(id_art)
					if fieldname == 'EB_Articoli.Codice':
						log.info("Assegnata l'immagine \"%s\" all'articolo con codice %s" % (original_filename, code_art))
					else:
						log.info("Assegnata l'immagine \"%s\" all'articolo con codice %s e %s %s" % (original_filename, code_art, fieldname_label, code))
	finally:
		if kongaui.is_progress_aborted():
			client.rollback_transaction()
			kongaui.close_progress()
		else:
			client.commit_transaction()
			kongaui.close_progress()
			kongautil.notify_data_changes('EB_Articoli', updated_arts)
			kongautil.notify_data_changes('EB_Articoli')
			kongautil.print_log(log, "Esito importazione immagini")



main()

