# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from datetime import datetime
import time
from openerp.osv import fields, osv
import openerp.addons.decimal_precision as dp

class stock_picking(osv.osv):
    _inherit="stock.picking"
    
    def create(self,cr,user,vals,context=None):
        list_picking=self.pool.get('stock.picking').search(cr,user,[('state','=','draft')])
        num=len(list_picking)+1 if (list_picking) else 1
        vals['name']='Borrador-'+str(num)
        vals['inka_number']='Borrador-'+str(num)
        vals['state']='draft'
        return super(stock_picking,self).create(cr,user,vals,context=context)
    
    def action_confirm(self, cr, uid, ids, context=None):
        self.write(cr,uid,ids,{'state':'draft'})
#         if(self.browse(cr,uid,ids[0]).state=='draft'):
#             name = self.pool.get('ir.sequence').get(cr, uid, 'stock.picking.out')
#             self.write(cr,uid,ids,{'name':name})
#             super(stock_picking,self).action_confirm(cr,uid,ids,context=context)
#         else:
        return True

    _columns={
              'inka_account_id': fields.many2one('account.account', 'Cuenta', required=True, readonly=True, states={'draft':[('readonly',False)]}),
              'inka_journal_id': fields.many2one('account.journal', 'Diario', required=True, readonly=True, states={'draft':[('readonly',False)]}),
              'inka_move_id':fields.many2one('account.move', 'Asiento contable', select=1, ondelete='restrict',readonly=True),
              'inka_number': fields.related('inka_move_id','name', type='char', readonly=True, size=64, relation='account.move', store=True, string='Number'),
              'inka_currency_id': fields.many2one('res.currency', 'Divisa', required=True, readonly=True, states={'draft':[('readonly',False)]}, track_visibility='always'),
              'inka_tax_line': fields.one2many('account.invoice.tax', 'inka_picking_id', 'Impuesto en Líneas', readonly=True),
              'inka_payment_term': fields.many2one('account.payment.term', 'Plazos de pago',readonly=True, states={'draft':[('readonly',False)]})
              }
                    
stock_picking()

class stock_picking_out(osv.osv):
    _inherit="stock.picking.out"
    
    def create(self,cr,usr,vals,context=None):
        return self.pool.get('stock.picking').create(cr,usr,vals,context=context)
    
    def inka_confirm(self, cr, uid, ids, context=None):
        #name = self.pool.get('ir.sequence').get(cr, uid, 'stock.picking.out')
        move_id,ref=self.inka_action_move_create(cr,uid,ids,context)
        if(move_id and ref):
            self.pool.get('account.move').write(cr,uid,[move_id],{'ref':ref})
            list_aml=self.pool.get('account.move.line').search(cr,uid,[('move_id','=',move_id)])
            self.pool.get('account.move.line').write(cr,uid,list_aml[0],{'ref':ref,'name':ref})
            list_aal=self.pool.get('account.analytic.line').search(cr,uid,[('move_id','=',move_id),('id','=',move_id)])
            for l in list_aal:
                self.pool.get('account.move.line').write(cr,uid,l,{'ref':ref})
        return self.action_confirm(cr,uid,ids,context=context)
    
    def _get_inka_journal(self, cr, uid, context=None):
        user = self.pool.get('res.users').browse(cr, uid, uid, context=context)
        company_id = context.get('company_id', user.company_id.id)
        journal_obj = self.pool.get('account.journal')
        #domain = [('company_id', '=', company_id)]
        domain=[('type', '=', 'sale')]
        res = journal_obj.search(cr, uid, domain, limit=1)
        return res and res[0] or False
    
    def _get_inka_currency(self, cr, uid, context=None):
        res = False
        journal_id = self._get_inka_journal(cr, uid, context=context)
        if journal_id:
            journal = self.pool.get('account.journal').browse(cr, uid, journal_id, context=context)
            res = journal.currency and journal.currency.id or journal.company_id.currency_id.id
        return res

    def _get_analytic_lines(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        obj_stock_picking = self.browse(cr, uid, id)
        cur_obj = self.pool.get('res.currency')
 
        company_currency = self.pool['res.company'].browse(cr, uid, obj_stock_picking.company_id.id).currency_id.id
        sign = 1
        list_picking_out_line = self.pool.get('stock.move').inka_move_line_get(cr, uid,id, context=context)
        for il in list_picking_out_line:
            if il['account_analytic_id']:
                ref = self.pool.get('account.invoice')._convert_ref(cr, uid, obj_stock_picking.inka_number)
                if not obj_stock_picking.inka_journal_id.analytic_journal_id:
                    raise osv.except_osv(_('No Analytic Journal!'),_("You have to define an analytic journal on the '%s' journal!") % (obj_stock_picking.inka_journal_id.name,))
                il['analytic_lines'] = [(0,0, {
                    'name': il['name'],
                    'date': obj_stock_picking['date'],
                    'account_id': il['account_id'],
                    'unit_amount': il['quantity'],
                    'amount': cur_obj.compute(cr, uid, obj_stock_picking.inka_currency_id.id, company_currency, il['price'], context={'date': obj_stock_picking.date}),
                    'product_id': il['product_id'],
                    'product_uom_id': il['uos_id'],
                    'general_account_id': il['account_id'],
                    'journal_id': obj_stock_picking.inka_journal_id.analytic_journal_id.id,
                    'ref': ref,
                })]
        return list_picking_out_line
    
    def inka_compute_invoice_totals(self, cr, uid, inv, company_currency, ref, invoice_move_lines, context=None):
        if context is None:
            context={}
        total = 0
        total_currency = 0
        cur_obj = self.pool.get('res.currency')
        for i in invoice_move_lines:
            if inv.inka_currency_id.id != company_currency:
                context.update({'date': inv.date or time.strftime('%Y-%m-%d')})
                i['currency_id'] = inv.inka_currency_id.id
                i['amount_currency'] = i['price']
                i['price'] = cur_obj.compute(cr, uid, inv.inka_currency_id.id,
                        company_currency, i['price'],
                        context=context)
            else:
                i['amount_currency'] = False
                i['currency_id'] = False
            i['ref'] = ref
            total += i['price']
            total_currency += i['amount_currency'] or i['price']
            i['price'] = - i['price']
        return total, total_currency, invoice_move_lines
    
    def inka_group_lines(self, cr, uid, iml, line, inv):
        """Merge account move lines (and hence analytic lines) if invoice line hashcodes are equals"""
        if inv.inka_journal_id.group_invoice_lines:
            line2 = {}
            for x, y, l in line:
                tmp = self.inv_line_characteristic_hashcode(inv, l)

                if tmp in line2:
                    am = line2[tmp]['debit'] - line2[tmp]['credit'] + (l['debit'] - l['credit'])
                    line2[tmp]['debit'] = (am > 0) and am or 0.0
                    line2[tmp]['credit'] = (am < 0) and -am or 0.0
                    line2[tmp]['tax_amount'] += l['tax_amount']
                    line2[tmp]['analytic_lines'] += l['analytic_lines']
                else:
                    line2[tmp] = l
            line = []
            for key, val in line2.items():
                line.append((0,0,val))
        return line
    
    def inka_check_tax_lines(self, cr, uid, inv, compute_taxes, ait_obj):
        company_currency = self.pool['res.company'].browse(cr, uid, inv.company_id.id).currency_id
        if not inv.inka_tax_line:
            for tax in compute_taxes.values():
                ait_obj.create(cr, uid, tax)
    
    def inka_compute(self, cr, uid, invoice_id, context=None):
        tax_grouped = {}
        tax_obj = self.pool.get('account.tax')
        cur_obj = self.pool.get('res.currency')
        inv = self.browse(cr, uid, invoice_id, context=context)
        cur = inv.inka_currency_id
        company_currency = self.pool['res.company'].browse(cr, uid, inv.company_id.id).currency_id.id
        for line in inv.move_lines:
            for tax in tax_obj.compute_all(cr, uid, line.inka_invoice_line_tax_id, (line.inka_price_unit* (1-(line.inka_discount or 0.0)/100.0)), line.product_qty, line.product_id, inv.partner_id)['taxes']:
                val={}
                val['inka_picking_id'] = inv.id
                val['name'] = tax['name']
                val['amount'] = tax['amount']
                val['manual'] = False
                val['sequence'] = tax['sequence']
                val['base'] = cur_obj.round(cr, uid, cur, tax['price_unit'] * line['product_qty'])

                val['base_code_id'] = tax['base_code_id']
                val['tax_code_id'] = tax['tax_code_id']
                val['base_amount'] = cur_obj.compute(cr, uid, inv.inka_currency_id.id, company_currency, val['base'] * tax['base_sign'], context={'date': inv.date or time.strftime('%Y-%m-%d')}, round=False)
                val['tax_amount'] = cur_obj.compute(cr, uid, inv.inka_currency_id.id, company_currency, val['amount'] * tax['tax_sign'], context={'date': inv.date or time.strftime('%Y-%m-%d')}, round=False)
                val['account_id'] = tax['account_collected_id'] or line.account_id.id
                val['account_analytic_id'] = tax['account_analytic_collected_id']

                key = (val['tax_code_id'], val['base_code_id'], val['account_id'], val['account_analytic_id'])
                if not key in tax_grouped:
                    tax_grouped[key] = val
                else:
                    tax_grouped[key]['amount'] += val['amount']
                    tax_grouped[key]['base'] += val['base']
                    tax_grouped[key]['base_amount'] += val['base_amount']
                    tax_grouped[key]['tax_amount'] += val['tax_amount']

        for t in tax_grouped.values():
            t['base'] = cur_obj.round(cr, uid, cur, t['base'])
            t['amount'] = cur_obj.round(cr, uid, cur, t['amount'])
            t['base_amount'] = cur_obj.round(cr, uid, cur, t['base_amount'])
            t['tax_amount'] = cur_obj.round(cr, uid, cur, t['tax_amount'])
        return tax_grouped
    
    def inka_action_move_create(self, cr, uid, ids, context=None):
        ait_obj = self.pool.get('account.invoice.tax')
        cur_obj = self.pool.get('res.currency')
        period_obj = self.pool.get('account.period')
        payment_term_obj = self.pool.get('account.payment.term')
        journal_obj = self.pool.get('account.journal')
        move_obj = self.pool.get('account.move')
        iml=[]
        if context is None:
            context = {}
        for obj_picking_out in self.browse(cr, uid, ids, context=context):
            if not obj_picking_out.inka_journal_id.sequence_id:
                raise osv.except_osv(('Error!'), ('Defina la sequencia del diario.'))
            if not obj_picking_out.move_lines:
                raise osv.except_osv(('No existe líneas de albarán!'), ('Ingrese algunos productos!'))
            if obj_picking_out.inka_move_id:
                continue
            ctx = context.copy()
            ctx.update({'lang': obj_picking_out.partner_id.lang})
            
            company_currency = self.pool['res.company'].browse(cr, uid, obj_picking_out.company_id.id).currency_id.id
            
            iml = self._get_analytic_lines(cr, uid, obj_picking_out.id, context=ctx)
            compute_taxes = self.inka_compute(cr, uid, obj_picking_out.id, context=ctx)
            self.inka_check_tax_lines(cr, uid, obj_picking_out, compute_taxes, ait_obj) #se crea el objeto impuesto de la facturar(albaran)
            
            iml += ait_obj.inka_move_line_get(cr, uid, obj_picking_out.id)
            entry_type = ''
            ref = self.pool.get('account.invoice')._convert_ref(cr, uid, obj_picking_out.inka_number)
            entry_type = 'journal_sale_vou'
            
            diff_currency_p = obj_picking_out.inka_currency_id.id <> company_currency
            total = 0
            total_currency = 0
            total, total_currency, iml = self.inka_compute_invoice_totals(cr, uid, obj_picking_out, company_currency, ref, iml, context=ctx)
            acc_id = obj_picking_out.inka_account_id.id
            name = obj_picking_out.name or '/'
            totlines = False
            
            if obj_picking_out.inka_payment_term:
                picking_date=obj_picking_out.date[0:10] if obj_picking_out.date else False
                totlines = payment_term_obj.compute(cr,uid, obj_picking_out.inka_payment_term.id, total,picking_date, context=ctx)
            if totlines:
                res_amount_currency = total_currency
                i = 0
                ctx.update({'date': obj_picking_out.date})
                for t in totlines:
                    if obj_picking_out.inka_currency_id.id != company_currency:
                        amount_currency = cur_obj.compute(cr, uid, company_currency, obj_picking_out.inka_currency_id.id, t[1], context=ctx)
                    else:
                        amount_currency = False

                    # last line add the diff
                    res_amount_currency -= amount_currency or 0
                    i += 1
                    if i == len(totlines):
                        amount_currency += res_amount_currency

                    iml.append({
                        'type': 'dest',
                        'name': name,
                        'price': t[1],
                        'account_id': acc_id,
                        'date_maturity': t[0],
                        'amount_currency': diff_currency_p \
                                and amount_currency or False,
                        'currency_id': diff_currency_p \
                                and obj_picking_out.currency_id.id or False,
                        'ref': ref,
                    })
            else:
                iml.append({
                    'type': 'dest',
                    'name': name,
                    'price': total,
                    'account_id': acc_id,
                    'date_maturity': False,
                    'amount_currency': diff_currency_p \
                            and total_currency or False,
                    'currency_id': diff_currency_p \
                            and obj_picking_out.currency_id.id or False,
                    'ref': ref
            })

            date = obj_picking_out.date or datetime.now().strftime('%Y-%m-%d')

            part = self.pool.get("res.partner")._find_accounting_partner(obj_picking_out.partner_id)

            line = map(lambda x:(0,0,self.pool.get('account.invoice').line_get_convert(cr, uid, x, part.id, date, context=ctx)),iml)

            line = self.inka_group_lines(cr, uid, iml, line, obj_picking_out)
            journal_id=obj_picking_out.inka_journal_id.id
            journal = journal_obj.browse(cr, uid, journal_id, context=ctx)
            if journal.centralisation:
                raise osv.except_osv(('User Error!'),
                        ('You cannot create an invoice on a centralized journal. Uncheck the centralized counterpart box in the related journal from the configuration menu.'))
            line = self.pool.get('account.invoice').finalize_invoice_move_lines(cr, uid, obj_picking_out, line)
            move = {
                    'ref': obj_picking_out.name,
                    'line_id': line,
                    'journal_id': journal_id,
                    'date': date,
                    'company_id': obj_picking_out.company_id.id,
                    }
            period_ids = period_obj.find(cr, uid, obj_picking_out.date, context=ctx)
            period_id = period_ids and period_ids[0] or False
            ctx.update(company_id=obj_picking_out.company_id.id,account_period_prefer_normal=True)
            if not period_id:
                period_ids = period_obj.find(cr, uid, obj_picking_out.date, context=ctx)
                period_id = period_ids and period_ids[0] or False
            if period_id:
                move['period_id'] = period_id
                for i in line:
                    i[2]['period_id'] = period_id
            ctx.update(invoice=period_obj)
            move_id = move_obj.create(cr, uid, move)            
            self.write(cr, uid, [obj_picking_out.id], {'inka_move_id': move_id})
            name=move_obj.inka_post(cr, uid, [move_id], context)#genera la secuencia del move y acutaliza las líneas
            self.write(cr, uid, [obj_picking_out.id], {'name':name})
            ref=self.pool.get('account.invoice')._convert_ref(cr, uid, name)            
        return move_id,ref
    
    _columns={
              'inka_account_id': fields.many2one('account.account', 'Cuenta', required=True, readonly=True, states={'draft':[('readonly',False)]}),
              'inka_journal_id': fields.many2one('account.journal', 'Diario', required=True, readonly=True, states={'draft':[('readonly',False)]}),
              'inka_move_id':fields.many2one('account.move', 'Asiento contable', select=1, ondelete='restrict',readonly=True),
              'inka_number': fields.related('inka_move_id','name', type='char', readonly=True, size=64, relation='account.move', store=True, string='Number'),
              'inka_currency_id': fields.many2one('res.currency', 'Divisa', required=True, readonly=True, states={'draft':[('readonly',False)]}, track_visibility='always'),
              'inka_tax_line': fields.one2many('account.invoice.tax', 'inka_picking_id', 'Impuesto en Líneas', readonly=True),
              'inka_payment_term': fields.many2one('account.payment.term', 'Plazos de pago',readonly=True, states={'draft':[('readonly',False)]})
              }
    
    _defaults={
               'inka_journal_id':_get_inka_journal,
               'inka_currency_id':_get_inka_currency
               }
stock_picking_out()

class stock_move(osv.osv):
    _inherit="stock.move"

    def inka_move_line_get_item(self, cr, uid, line, context=None):
        return {
            'type':'src',
            'name': line.name.split('\n')[0][:64],
            'price_unit':line.inka_price_unit,
            'quantity':line.product_qty,
            'price':line.inka_price_subtotal,
            'account_id':line.inka_account_id.id,
            'product_id':line.product_id.id,
            'uos_id':line.product_uom.id,
            'account_analytic_id':False,
            'taxes':line.inka_invoice_line_tax_id,
        }
    
    def inka_move_line_get(self, cr, uid, picking_id, context=None):
        res = []
        tax_obj = self.pool.get('account.tax')
        cur_obj = self.pool.get('res.currency')
        if context is None:
            context = {}
        obj_stock_picking = self.pool.get('stock.picking').browse(cr, uid, picking_id, context=context)
        company_currency = self.pool['res.company'].browse(cr, uid, obj_stock_picking.company_id.id).currency_id.id
        for line in obj_stock_picking.move_lines:
            list_line = self.inka_move_line_get_item(cr, uid, line, context)     #pendiente#####
            if not list_line:
                continue
            res.append(list_line)
            tax_code_found= False
            for tax in tax_obj.compute_all(cr, uid, line.inka_invoice_line_tax_id,
                    (line.inka_price_unit * (1.0 - (line['inka_discount'] or 0.0) / 100.0)),
                    line.product_qty, line.product_id,
                    obj_stock_picking.partner_id)['taxes']:
                
                tax_code_id = tax['base_code_id']
                tax_amount = line.inka_price_subtotal * tax['base_sign']

                if tax_code_found:
                    if not tax_code_id:
                        continue
                    res.append(self.inka_move_line_get_item(cr, uid, line, context))
                    res[-1]['price'] = 0.0
                    res[-1]['account_analytic_id'] = False
                elif not tax_code_id:
                    continue
                tax_code_found = True

                res[-1]['tax_code_id'] = tax_code_id
                res[-1]['tax_amount'] = cur_obj.compute(cr, uid, obj_stock_picking.inka_currency_id.id, company_currency, tax_amount, context={'date': obj_stock_picking.date})
        return res  #account_analytic_id: false
    
    def onchange_product_id(self, cr, uid, ids, prod_id=False, loc_id=False,loc_dest_id=False, partner_id=False):
        val={}
        fpos_obj = self.pool.get('account.fiscal.position')
        val=super(stock_move,self).onchange_product_id(cr, uid, ids, prod_id, loc_id,loc_dest_id, partner_id)
        if (prod_id):
            obj_product = self.pool.get('product.product').browse(cr, uid, prod_id)
            if(obj_product):
                a = obj_product.property_account_income.id
                if not a:
                    a = obj_product.categ_id.property_account_income_categ.id
                else:
                    a = obj_product.property_account_expense.id
                    if not a:
                        a = obj_product.categ_id.property_account_expense_categ.id
                a = fpos_obj.map_account(cr, uid, False, a)
                if a:
                    val['value'].update({'inka_account_id':a})
                val['value'].update({'inka_price_unit':obj_product.list_price})
                
                taxes = obj_product.taxes_id and obj_product.taxes_id or (a and self.pool.get('account.account').browse(cr, uid, a).tax_ids or False)
                tax_id = fpos_obj.map_tax(cr, uid, False, taxes)
                val['value'].update({'inka_invoice_line_tax_id':tax_id})
        return val
    
    def _inka_amount_line_func(self, cr, uid, ids, field_name, args, context=None):
        res = {}
        tax_obj = self.pool.get('account.tax')
        cur_obj = self.pool.get('res.currency')
        for line in self.browse(cr, uid, ids):
            price = line.inka_price_unit * (1-(line.inka_discount or 0.0)/100.0)
            print line.product_qty
            taxes = tax_obj.compute_all(cr, uid, line.inka_invoice_line_tax_id, price, line.product_qty, product=line.product_id, partner=line.picking_id.partner_id)
            res[line.id] = taxes['total']
#             if line.picking_id:
#                 cur = line.picking_id.inka_currency_id
#                 res[line.id] = cur_obj.round(cr, uid, cur, res[line.id])
        return res
        
    _columns={
              'inka_account_id': fields.many2one('account.account', 'Account', required=True, readonly=True, states={'draft':[('readonly',False)]}),
              'inka_price_unit':fields.float('Precio Unitario', required=True),
              'inka_invoice_line_tax_id': fields.many2many('account.tax', 'inka_stock_move_line_tax', 'invoice_line_id', 'tax_id', 'Impuesto', domain=[('parent_id','=',False)]),
              'inka_price_subtotal': fields.function(_inka_amount_line_func, type='float', string='Sub Total',digits_compute= dp.get_precision('Account')),
              'inka_discount': fields.float('Descuento %')
              }
    
    _defaults={
               'inka_discount':0.0
               }
        
stock_move()

class account_move(osv.osv):
    _inherit="account.move"
    
    def inka_post(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        invoice = context.get('invoice', False)
        valid_moves = self.validate(cr, uid, ids, context)
        if not valid_moves:
            raise osv.except_osv(('Error!'), ('You cannot validate a non-balanced entry.\nMake sure you have configured payment terms properly.\nThe latest payment term line should be of the "Balance" type.'))        
        obj_sequence = self.pool.get('ir.sequence')
        for obj_move in self.browse(cr, uid, valid_moves, context=context):
            if obj_move.name =='/':
                new_name = False
                journal = obj_move.journal_id
            if journal.sequence_id:
                c = {'fiscalyear_id': obj_move.period_id.fiscalyear_id.id}
                new_name = obj_sequence.next_by_id(cr, uid, journal.sequence_id.id, c)
            else:
                raise osv.except_osv(('Error!'), ('Please define a sequence on the journal.'))
            if new_name:
                    self.write(cr, uid, ids, {'name':new_name})
        cr.execute('UPDATE account_move '\
                   'SET state=%s '\
                   'WHERE id IN %s',
                   ('posted', tuple(valid_moves),))
                   #('posted', tuple(ids),))
        return new_name

account_move()

class account_invoice_tax(osv.osv):
    _inherit = "account.invoice.tax"
    _columns={
              'inka_picking_id': fields.many2one('stock.picking', 'Albarán', ondelete='cascade', select=True),
              }
    
    def inka_move_line_get(self, cr, uid, invoice_id):
        res = []
        cr.execute('SELECT * FROM account_invoice_tax WHERE inka_picking_id=%s', (invoice_id,))
        for t in cr.dictfetchall():
            if not t['amount'] \
                    and not t['tax_code_id'] \
                    and not t['tax_amount']:
                continue
            res.append({
                'type':'tax',
                'name':t['name'],
                'price_unit': t['amount'],
                'quantity': 1,
                'price': t['amount'] or 0.0,
                'account_id': t['account_id'],
                'tax_code_id': t['tax_code_id'],
                'tax_amount': t['tax_amount'],
                'account_analytic_id': t['account_analytic_id'],
            })
        return res
    
    
account_invoice_tax()
    