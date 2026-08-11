from flask import Blueprint, render_template, redirect, url_for, flash, request, g, abort
from controllers.decorators import login_required
from models import db, FileRecord
from models.room import Room, RoomMembership, RoomInviteCode, RoomFile, ROLE_OWNER
from services.room_service import RoomService, VALID_ROLES

rooms_bp = Blueprint("rooms", __name__)


# ── Lista pokoi użytkownika ────────────────────────────────────────────────────

@rooms_bp.route("/rooms")
@login_required
def rooms_list():
    memberships = (
        RoomMembership.query
        .filter_by(user_id=g.user.id)
        .join(Room)
        .order_by(Room.name)
        .all()
    )
    return render_template("rooms/list.html", memberships=memberships)


# ── Dołącz przez kod ──────────────────────────────────────────────────────────

@rooms_bp.route("/rooms/join", methods=["POST"])
@login_required
def join_room():
    code = request.form.get("code", "").strip()
    room, err = RoomService.join_by_code(g.user, code)
    if err:
        flash(err, "danger")
        return redirect(url_for("rooms.rooms_list"))
    flash(f'Dołączyłeś do pokoju "{room.name}"!', "success")
    return redirect(url_for("rooms.room_view", room_id=room.id))


# ── Utwórz pokój ─────────────────────────────────────────────────────────────

@rooms_bp.route("/rooms/create", methods=["POST"])
@login_required
def create_room():
    name = request.form.get("name", "").strip()
    desc = request.form.get("description", "").strip()
    room, err = RoomService.create(g.user, name, desc)
    if err:
        flash(err, "danger")
        return redirect(url_for("rooms.rooms_list"))
    flash(f'Pokój "{room.name}" został utworzony.', "success")
    return redirect(url_for("rooms.room_view", room_id=room.id))


# ── Widok pokoju ──────────────────────────────────────────────────────────────

@rooms_bp.route("/rooms/<int:room_id>")
@login_required
def room_view(room_id):
    room = Room.query.get_or_404(room_id)
    membership = RoomService.get_membership(room, g.user)
    if not membership:
        abort(403)

    members = (
        RoomMembership.query
        .filter_by(room_id=room.id)
        .all()
    )
    from models.room import RoomFolder
    subfolders = (
        RoomFolder.query
        .filter_by(room_id=room.id, parent_id=None)
        .order_by(RoomFolder.name)
        .all()
    )
    room_files = (
        RoomFile.query
        .filter_by(room_id=room.id, folder_id=None)
        .order_by(RoomFile.uploaded_at.desc())
        .all()
    )
    invites = []
    if membership.can_generate_invite():
        invites = (
            RoomInviteCode.query
            .filter_by(room_id=room.id)
            .order_by(RoomInviteCode.created_at.desc())
            .all()
        )

    # Własne pliki użytkownika (do udostępniania w pokoju)
    my_files = (
        FileRecord.query
        .filter_by(user_id=g.user.id)
        .order_by(FileRecord.created_at.desc())
        .all()
    ) if membership.can_upload() else []

    # Zbiór ID plików już dodanych
    shared_file_ids = {rf.file_record_id for rf in room_files}

    return render_template(
        "rooms/room.html",
        room=room,
        membership=membership,
        members=members,
        subfolders=subfolders,
        room_files=room_files,
        current_folder=None,
        breadcrumbs=[],
        invites=invites,
        my_files=my_files,
        shared_file_ids=shared_file_ids,
        valid_roles=list(VALID_ROLES),
        ROLE_OWNER=ROLE_OWNER,
    )


# ── Usuń pokój ───────────────────────────────────────────────────────────────

@rooms_bp.route("/rooms/<int:room_id>/delete", methods=["POST"])
@login_required
def delete_room(room_id):
    room = Room.query.get_or_404(room_id)
    ok, err = RoomService.delete(room, g.user)
    if not ok:
        flash(err, "danger")
        return redirect(url_for("rooms.room_view", room_id=room_id))
    flash("Pokój został usunięty.", "success")
    return redirect(url_for("rooms.rooms_list"))


# ── Opuść pokój ───────────────────────────────────────────────────────────────

@rooms_bp.route("/rooms/<int:room_id>/leave", methods=["POST"])
@login_required
def leave_room(room_id):
    room = Room.query.get_or_404(room_id)
    ok, err = RoomService.leave(room, g.user)
    if not ok:
        flash(err, "danger")
        return redirect(url_for("rooms.room_view", room_id=room_id))
    flash(f'Opuściłeś pokój "{room.name}".', "info")
    return redirect(url_for("rooms.rooms_list"))


# ── Zmień rolę członka ────────────────────────────────────────────────────────

@rooms_bp.route("/rooms/<int:room_id>/members/<int:target_id>/role", methods=["POST"])
@login_required
def set_member_role(room_id, target_id):
    room = Room.query.get_or_404(room_id)
    new_role = request.form.get("role", "")
    ok, err = RoomService.set_role(room, g.user, target_id, new_role)
    if not ok:
        flash(err, "danger")
    else:
        flash("Rola została zmieniona.", "success")
    return redirect(url_for("rooms.room_view", room_id=room_id))


# ── Wyrzuć członka ────────────────────────────────────────────────────────────

@rooms_bp.route("/rooms/<int:room_id>/members/<int:target_id>/kick", methods=["POST"])
@login_required
def kick_member(room_id, target_id):
    room = Room.query.get_or_404(room_id)
    ok, err = RoomService.kick(room, g.user, target_id)
    if not ok:
        flash(err, "danger")
    else:
        flash("Użytkownik został usunięty z pokoju.", "success")
    return redirect(url_for("rooms.room_view", room_id=room_id))


# ── Generuj kod zaproszenia ───────────────────────────────────────────────────

@rooms_bp.route("/rooms/<int:room_id>/invite", methods=["POST"])
@login_required
def create_invite(room_id):
    room = Room.query.get_or_404(room_id)
    role = request.form.get("role", "viewer")
    expires_hours = request.form.get("expires_hours", "24")
    invite, err = RoomService.create_invite(room, g.user, role, expires_hours)
    if err:
        flash(err, "danger")
    else:
        flash(f"Kod zaproszenia: {invite.code}", "success")
    return redirect(url_for("rooms.room_view", room_id=room_id))


# ── Unieważnij kod zaproszenia ────────────────────────────────────────────────

@rooms_bp.route("/rooms/invite/<int:invite_id>/revoke", methods=["POST"])
@login_required
def revoke_invite(invite_id):
    invite = RoomInviteCode.query.get_or_404(invite_id)
    room_id = invite.room_id
    ok, err = RoomService.revoke_invite(invite, g.user)
    if not ok:
        flash(err, "danger")
    else:
        flash("Kod zaproszenia został unieważniony.", "info")
    return redirect(url_for("rooms.room_view", room_id=room_id))


# ── Dodaj plik do pokoju ──────────────────────────────────────────────────────

@rooms_bp.route("/rooms/<int:room_id>/files/add", methods=["POST"])
@login_required
def add_file(room_id):
    room = Room.query.get_or_404(room_id)
    file_id = request.form.get("file_id", type=int)
    folder_id_raw = request.form.get("folder_id", "").strip()
    folder_id = int(folder_id_raw) if folder_id_raw and folder_id_raw.isdigit() else None
    file_record = FileRecord.query.get_or_404(file_id)
    _, err = RoomService.add_file(room, file_record, g.user, folder_id=folder_id)
    if err:
        flash(err, "danger")
    else:
        flash(f'Plik "{file_record.original_name}" dodany do pokoju.', "success")
    if folder_id:
        return redirect(url_for("rooms.folder_view", room_id=room_id, folder_id=folder_id))
    return redirect(url_for("rooms.room_view", room_id=room_id))


# ── Usuń plik z pokoju ────────────────────────────────────────────────────────

@rooms_bp.route("/rooms/<int:room_id>/files/<int:room_file_id>/remove", methods=["POST"])
@login_required
def remove_file(room_id, room_file_id):
    room = Room.query.get_or_404(room_id)
    room_file = RoomFile.query.get_or_404(room_file_id)
    if room_file.room_id != room_id:
        abort(404)
    ok, err = RoomService.remove_file(room, room_file, g.user)
    if not ok:
        flash(err, "danger")
    else:
        flash("Plik usunięty z pokoju.", "info")
    return redirect(url_for("rooms.room_view", room_id=room_id))


# ── Podfoldery ────────────────────────────────────────────────────────────────

@rooms_bp.route("/rooms/<int:room_id>/folders/create", methods=["POST"])
@login_required
def create_folder(room_id):
    room = Room.query.get_or_404(room_id)
    name = request.form.get("name", "").strip()
    parent_id = request.form.get("parent_id", "").strip()
    parent_id = int(parent_id) if parent_id and parent_id.isdigit() else None
    _, err = RoomService.create_folder(room, g.user, name, parent_id)
    if err:
        flash(err, "danger")
    else:
        flash(f'Folder "{name}" zostal utworzony.', "success")
    if parent_id:
        return redirect(url_for("rooms.folder_view", room_id=room_id, folder_id=parent_id))
    return redirect(url_for("rooms.room_view", room_id=room_id))


@rooms_bp.route("/rooms/<int:room_id>/folders/<int:folder_id>")
@login_required
def folder_view(room_id, folder_id):
    from models.room import RoomFolder
    room = Room.query.get_or_404(room_id)
    membership = RoomService.get_membership(room, g.user)
    if not membership:
        abort(403)

    folder = RoomFolder.query.filter_by(id=folder_id, room_id=room_id).first_or_404()
    subfolders = RoomFolder.query.filter_by(room_id=room_id, parent_id=folder_id).order_by(RoomFolder.name).all()
    room_files = RoomFile.query.filter_by(room_id=room_id, folder_id=folder_id).order_by(RoomFile.uploaded_at.desc()).all()

    # Breadcrumbs
    breadcrumbs = []
    node = folder
    while node:
        breadcrumbs.insert(0, node)
        node = node.parent

    members = RoomMembership.query.filter_by(room_id=room.id).all()
    invites = []
    if membership.can_generate_invite():
        invites = RoomInviteCode.query.filter_by(room_id=room.id).order_by(RoomInviteCode.created_at.desc()).all()

    my_files = (
        FileRecord.query.filter_by(user_id=g.user.id).order_by(FileRecord.created_at.desc()).all()
        if membership.can_upload() else []
    )
    shared_file_ids = {rf.file_record_id for rf in room_files}

    return render_template(
        "rooms/room.html",
        room=room,
        membership=membership,
        members=members,
        room_files=room_files,
        subfolders=subfolders,
        current_folder=folder,
        breadcrumbs=breadcrumbs,
        invites=invites,
        my_files=my_files,
        shared_file_ids=shared_file_ids,
        valid_roles=list(VALID_ROLES),
        ROLE_OWNER=ROLE_OWNER,
    )


@rooms_bp.route("/rooms/<int:room_id>/folders/<int:folder_id>/delete", methods=["POST"])
@login_required
def delete_folder(room_id, folder_id):
    from models.room import RoomFolder
    room = Room.query.get_or_404(room_id)
    folder = RoomFolder.query.filter_by(id=folder_id, room_id=room_id).first_or_404()
    parent_id = folder.parent_id
    ok, err = RoomService.delete_folder(room, g.user, folder)
    if not ok:
        flash(err, "danger")
    else:
        flash("Folder usuniety.", "success")
    if parent_id:
        return redirect(url_for("rooms.folder_view", room_id=room_id, folder_id=parent_id))
    return redirect(url_for("rooms.room_view", room_id=room_id))


@rooms_bp.route("/rooms/<int:room_id>/folders/<int:folder_id>/rename", methods=["POST"])
@login_required
def rename_folder(room_id, folder_id):
    from models.room import RoomFolder
    room = Room.query.get_or_404(room_id)
    folder = RoomFolder.query.filter_by(id=folder_id, room_id=room_id).first_or_404()
    new_name = request.form.get("name", "").strip()
    ok, err = RoomService.rename_folder(room, g.user, folder, new_name)
    if not ok:
        flash(err, "danger")
    else:
        flash("Folder przemianowany.", "success")
    if folder.parent_id:
        return redirect(url_for("rooms.folder_view", room_id=room_id, folder_id=folder.parent_id))
    return redirect(url_for("rooms.room_view", room_id=room_id))

# ── Wgraj nowy plik bezpośrednio do pokoju ───────────────────────────────────

@rooms_bp.route("/rooms/<int:room_id>/files/upload", methods=["POST"])
@login_required
def upload_to_room(room_id):
    from services.file_service import FileService
    from flask import jsonify

    room = Room.query.get_or_404(room_id)
    membership = RoomService.get_membership(room, g.user)
    if not membership or not membership.can_upload():
        abort(403)

    folder_id_raw = request.form.get("folder_id", "").strip()
    folder_id = int(folder_id_raw) if folder_id_raw and folder_id_raw.isdigit() else None

    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Brak pliku."}), 400

    uploaded = 0
    errors = []
    for f in request.files.getlist("file"):
        record, err = FileService.save_upload(f, g.user)
        if err:
            errors.append(err)
            continue
        _, err2 = RoomService.add_file(room, record, g.user, folder_id=folder_id)
        if err2:
            errors.append(err2)
        else:
            uploaded += 1

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        if uploaded:
            return jsonify({"ok": True, "uploaded": uploaded})
        return jsonify({"ok": False, "error": "; ".join(errors)}), 400

    if uploaded:
        flash(f"Przesłano {uploaded} plik(ów) do pokoju.", "success")
    for e in errors:
        flash(e, "warning")

    if folder_id:
        return redirect(url_for("rooms.folder_view", room_id=room_id, folder_id=folder_id))
    return redirect(url_for("rooms.room_view", room_id=room_id))

# ── Pobierz plik z pokoju (dla wszystkich członków) ──────────────────────────

@rooms_bp.route("/rooms/<int:room_id>/files/<int:room_file_id>/download")
@login_required
def download_room_file(room_id, room_file_id):
    import os
    from flask import send_file
    from services.file_service import FileService

    room = Room.query.get_or_404(room_id)
    membership = RoomService.get_membership(room, g.user)
    if not membership:
        abort(403)

    room_file = RoomFile.query.filter_by(id=room_file_id, room_id=room_id).first_or_404()
    record = room_file.file_record
    if not record:
        abort(404)

    path = FileService.physical_path(record)
    if not os.path.exists(path):
        abort(404)

    return send_file(path, download_name=record.original_name, as_attachment=True)