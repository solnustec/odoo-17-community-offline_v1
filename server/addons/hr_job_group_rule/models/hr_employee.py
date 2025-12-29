from odoo import api, fields, models

class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def action_apply_job_group_rules(self):
        self.ensure_one()
        self._apply_job_group_rules(self)
        return True

    @api.model
    def _apply_job_group_rules(self, employees):
        """Aplica las reglas de grupos para una lista de empleados (recordset)."""
        employees = employees.filtered(lambda e: e.user_id and e.job_id)
        if not employees:
            return

        # Pre-carga
        all_jobs = employees.mapped("job_id")
        rules_by_job = {
            job.id: self.env["hr.job.group.rule"].search([("job_id", "=", job.id), ("active", "=", True)])
            for job in all_jobs
        }

        Users = self.env["res.users"].sudo()  # grupos necesitan sudo casi siempre
        Link = self.env["res.users.job_group_link"].sudo()

        for emp in employees:
            user = emp.user_id.sudo()
            job = emp.job_id
            rules = rules_by_job.get(job.id, self.env["hr.job.group.rule"])

            if not rules:
                # Opcional: si quieres quitar lo gestionado por el cargo anterior, hazlo en write() comparando viejo/nuevo
                continue

            # Grupos actuales del usuario (ids)
            current_group_ids = set(user.groups_id.ids)

            # Calcular "desired" por reglas activas
            desired_group_ids = set()
            for rule in rules:
                if rule.trigger_group_ids:
                    # Aplica si el usuario tiene ANY de los triggers
                    if current_group_ids.intersection(set(rule.trigger_group_ids.ids)):
                        desired_group_ids.update(rule.access_group_ids.ids)
                else:
                    # Sin trigger → siempre aplica
                    desired_group_ids.update(rule.access_group_ids.ids)

            if not desired_group_ids:
                continue

            # Tracking existente para este user por cualquier cargo
            existing_links = Link.search([("user_id", "=", user.id)])
            existing_pairs = {(l.group_id.id, l.job_id.id) for l in existing_links}
            existing_managed_groups = {l.group_id.id for l in existing_links if l.job_id.id == job.id}

            # Agregar los que faltan (add_only)
            to_add = desired_group_ids - current_group_ids
            if to_add:
                user.write({"groups_id": [(4, gid) for gid in to_add]})
                # crear tracking para cada agregado si no existía
                new_links_vals = []
                for gid in to_add:
                    if (gid, job.id) not in existing_pairs:
                        new_links_vals.append({"user_id": user.id, "group_id": gid, "job_id": job.id})
                if new_links_vals:
                    Link.create(new_links_vals)

            # Opcional: si quieres modo replace_managed a nivel de regla, podrías evaluar acá.
            # Por simplicidad, implementamos una limpieza prudente:
            # - Solo removeremos grupos que estén trackeados por ESTE cargo y que ya no estén "desired".
            # - No tocamos grupos no trackeados (manuales u otros módulos).
            to_remove_managed = existing_managed_groups - desired_group_ids
            if to_remove_managed:
                user.write({"groups_id": [(3, gid) for gid in to_remove_managed]})
                Link.search([
                    ("user_id", "=", user.id),
                    ("job_id", "=", job.id),
                    ("group_id", "in", list(to_remove_managed)),
                ]).unlink()

    def write(self, vals):
        job_changed = "job_id" in vals
        res = super().write(vals)

        if job_changed:
            Rule = self.env["hr.job.group.rule"].sudo()
            Link = self.env["res.users.job_group_link"].sudo()
            excluded_ids = {1, 2}  # OdooBot (1) y Admin (2)

            for emp in self.filtered(lambda e: e.user_id and e.job_id and e.user_id.id not in excluded_ids):
                user = emp.user_id.sudo()
                rules = Rule.search([("job_id", "=", emp.job_id.id), ("active", "=", True)])

                if not rules:
                    # Lo dejamos sin acción.
                    continue

                # 1) Calcula "desired" y si corresponde "replace"
                desired = set()
                replace = any(r.apply_mode == "replace_managed" for r in rules)
                for r in rules:
                    desired.update(r.access_group_ids.ids)

                # 2) Agregar faltantes
                current = set(user.groups_id.ids)
                to_add = desired - current
                if to_add:
                    user.write({"groups_id": [(4, gid) for gid in to_add]})
                    Link.create([
                        {"user_id": user.id, "group_id": gid, "job_id": emp.job_id.id}
                        for gid in to_add
                        if not Link.search_count(
                            [("user_id", "=", user.id), ("group_id", "=", gid), ("job_id", "=", emp.job_id.id)])
                    ])

                # 3) Quitar (solo si replace_managed está activo en alguna regla)
                if replace:
                    # Obtener todos los grupos gestionados por este job
                    managed_links = Link.search([("user_id", "=", user.id), ("job_id", "=", emp.job_id.id)])

                    # Grupos actuales del usuario
                    current_groups = set(user.groups_id.ids)

                    # Quitar TODOS los grupos actuales que no son deseados
                    # (esto incluye grupos que no están en la tabla intermedia)
                    all_to_remove = current_groups - desired

                    if all_to_remove:
                        user.write({"groups_id": [(3, gid) for gid in all_to_remove]})

                        # Eliminar los links de la tabla intermedia para los grupos que se quitaron
                        # y que estaban gestionados por este job
                        links_to_remove = managed_links.filtered(lambda l: l.group_id.id in all_to_remove)
                        if links_to_remove:
                            links_to_remove.unlink()

        return res