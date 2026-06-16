type Props = {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  confirmationValue?: string;
  confirmationInput?: string;
  onConfirmationInput?: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
};

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  confirmationValue,
  confirmationInput,
  onConfirmationInput,
  onCancel,
  onConfirm,
}: Props) {
  if (!open) return null;
  const blocked = Boolean(
    confirmationValue && confirmationInput !== confirmationValue,
  );
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="confirm-dialog" role="dialog" aria-modal="true">
        <h2>{title}</h2>
        <p>{message}</p>
        {confirmationValue && (
          <label className="field">
            <span>Escribe {confirmationValue} para confirmar</span>
            <input
              value={confirmationInput ?? ""}
              onChange={(event) => onConfirmationInput?.(event.target.value)}
            />
          </label>
        )}
        <div className="config-actions">
          <button className="button secondary" type="button" onClick={onCancel}>
            Cancelar
          </button>
          <button
            className="button danger"
            type="button"
            disabled={blocked}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
