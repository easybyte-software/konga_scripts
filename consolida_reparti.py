# -*- title: Consolida reparti POS -*-
# -*- coding: utf-8 -*-
# -*- py3k-safe -*-

from __future__ import print_function

import kongalib
import kongautil
import kongaui


TIPO_DESCRITTIVO = 4


FORM_FIELDS = [
	{
		'name': 'code_azienda',
		'label': "Codice azienda",
		'default': kongautil.get_window_vars().get('COMPANY_CODE', ''),
	},
	{
		'name': 'action',
		'label': "Tipo di correzione",
		'type': 'choice',
		'items': [
			"Assegna aliquota del reparto all'articolo",
			"Assegna reparto all'articolo in base all'aliquota",
		],
		'default': 0,
	},
	{
		'name': 'simulate',
		'label': "Esegui simulazione",
		'tip': "Simula tutte le operazioni ma non apportare modifiche; verrà mostrato un log riepilogativo",
		'type': 'bool',
		'default': True,
	}
]


def main():
	params = kongaui.execute_form(FORM_FIELDS,
			"Consolida reparti POS",
			"Questo script consolida i reparti POS degli articoli di magazzino per evitare disallineamenti tra l'aliquota IVA degli articoli e quella del reparto ed essi abbinato. Alla fine verrà mostrato un log riepilogativo con il risultato di tutte le operazioni simulate.<br/><br/>",
			condition = "code_azienda")
	if not params:
		return
	log = kongalib.Log()
	client = kongautil.connect()
	kongaui.open_progress('Consolidamento reparti in corso...')
	client.begin_transaction()
	try:
		vats = client.select_data('EB_AliquoteIVA', ['EB_AliquoteIVA.id', 'EB_AliquoteIVA.Codice', 'EB_AliquoteIVA.PercentualeIVA'])
		vat_to_id = { vat[1]: vat[0] for vat in vats }
		id_to_vat = { vat[0]: vat[2] for vat in vats }
		vat_to_code = { vat[0]: vat[1] for vat in vats }
		departments = client.select_data('EB_Reparti', ['EB_Reparti.id', 'EB_Reparti.NumeroReparto', 'EB_Reparti.ref_AliquotaIVA'])
		dep_to_vat_id = { dep[1]: dep[2] for dep in departments }
		vat_id_to_dep = { dep[2]: dep[1] for dep in departments }
		w_ex = kongalib.AND(kongalib.OperandNE('EB_Articoli.val_Tipo', TIPO_DESCRITTIVO), kongalib.OR(kongalib.OperandEQ('EB_Articoli.ref_Azienda.Codice', params['code_azienda']), kongalib.OperandIsNull('EB_Articoli.ref_Azienda')))
		products = client.select_data('EB_Articoli', ['EB_Articoli.id', 'EB_Articoli.Codice', 'EB_Articoli.ref_AliquotaIVA', 'EB_Articoli.NumeroReparto'], w_ex, 'EB_Articoli.Codice')
		for index, product in enumerate(products):
			kongaui.set_progress((index * 100.0) / len(products))
			if kongaui.is_progress_aborted():
				break
			prod_vat = id_to_vat.get(product[2], kongalib.Decimal(0))
			dep_vat_id = dep_to_vat_id.get(product[3], None)
			if dep_vat_id is None:
				log.error('L\'articolo "%s" ha numero di reparto %d, ma il reparto non esiste!' % (product[1], product[3]))
			else:
				dep_vat = id_to_vat[dep_vat_id]
				if dep_vat == prod_vat:
					if dep_vat_id != product[2]:
						log.warning('L\'articolo "%s" ha la percentuale dell\'aliquota IVA corrispodente alla percentuale dell\'aliquota IVA del reparto abbinato, ma le aliquote IVA si riferiscono a record differenti nella tabella delle aliquote IVA' % product[1])
				else:
					if params['action'] == 0:
						client.update_record('EB_Articoli', { 'EB_Articoli.ref_AliquotaIVA': dep_vat_id }, id=product[0])
						log.info('Assegnata l\'aliquota IVA "%s" del reparto %d all\'articolo "%s"' % (vat_to_code[dep_vat_id], product[3], product[1]))
					else:
						dep = vat_id_to_dep.get(product[2], None)
						if dep is None:
							if product[2] is None:
								log.error('Impossibile assegnare il reparto all\'articolo "%s": l\'articolo non ha aliquota IVA impostata' % product[1])
							else:
								log.error('Impossibile assegnare il reparto all\'articolo "%s": l\'aliquota IVA "%s" non ha un reparto associato' % (product[1], vat_to_code[product[2]]))
						else:
							client.update_record('EB_Articoli', { 'EB_Articoli.NumeroReparto': dep }, id=product[0])
							log.info('Assegnato il reparto %d con aliquota IVA "%s" all\'articolo "%s"' % (dep, vat_to_code[dep_to_vat_id[dep]], product[1]))
	finally:
		if kongaui.is_progress_aborted():
			client.rollback_transaction()
			kongaui.close_progress()
		else:
			if log.has_errors() or params['simulate']:
				client.rollback_transaction()
			else:
				client.commit_transaction()
			kongaui.close_progress()
			kongautil.print_log(log, "Esito %sconsolidamento reparti POS" % ('simulazione ' if params['simulate'] else ''))


main()

