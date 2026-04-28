import os

src_file = r'e:\Anigravity\Legalize_site\Legalize_site-1\static\clients\js\client_detail.js'
dest_dir = r'e:\Anigravity\Legalize_site\Legalize_site-1\static\clients\js\client'

if not os.path.exists(dest_dir):
    os.makedirs(dest_dir)

with open(src_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Strip IIFE
start_idx = 1
end_idx = len(lines) - 2

content = lines[start_idx:end_idx]

# We need to unindent everything by 2 spaces.
content = [line[2:] if line.startswith('  ') else line for line in content]

# Let's just group lines by their logic.
def extract_lines(start_str, end_str):
    s, e = -1, -1
    for i, line in enumerate(content):
        if start_str in line and s == -1:
            s = i
        if end_str in line and s != -1:
            e = i
            break
    if s == -1 or e == -1:
        return []
    res = content[s:e+1]
    for i in range(e, s-1, -1):
        del content[i]
    return res

ajax_lines = []
ajax_lines.extend(extract_lines('function createTemplateFragment', 'return template.content;\n}\n'))
ajax_lines.extend(extract_lines('function replaceNodeContents', '  node.replaceChildren(createTemplateFragment(html));\n}\n'))
ajax_lines.extend(extract_lines('function buildAjaxHeaders', '  return merged;\n}\n'))
ajax_lines.extend(extract_lines('function buildAjaxOptions', '  };\n}\n'))
ajax_lines.extend(extract_lines('function normalizeResponsePreview', '  return (text || \'\').replace(/\\s+/g, \' \').trim().slice(0, 240);\n}\n'))
ajax_lines.extend(extract_lines('function buildResponseError', '  return error;\n}\n'))
ajax_lines.extend(extract_lines('async function readJsonPayload', '  }\n}\n'))
ajax_lines.extend(extract_lines('async function fetchJson', '  return { response, data };\n}\n'))
ajax_lines.extend(extract_lines('async function fetchHtml', '  return { response, html: await response.text() };\n}\n'))
ajax_lines.extend(extract_lines('function logAjaxError', '  });\n}\n'))
ajax_lines.extend(extract_lines('function showAlert', '  }, 3500);\n}\n'))
ajax_lines.extend(extract_lines('function showPaymentAlert', '  showAlert(\'payment-alerts\', message, type);\n}\n'))
ajax_lines.extend(extract_lines('function showDocumentAlert', '  showAlert(\'document-alerts\', message, type);\n}\n'))
ajax_lines.extend(extract_lines('function getErrorMessage', '  return fallbackMessage;\n}\n'))

payments_lines = []
payments_lines.extend(extract_lines('function initPriceAutoFill', '  });\n}\n'))
payments_lines.extend(extract_lines('function prependPaymentItem', '  list.prepend(newItem);\n}\n'))
payments_lines.extend(extract_lines('function updatePaymentItem', '  }\n}\n'))
payments_lines.extend(extract_lines('function removePaymentItem', '  }\n}\n'))
payments_lines.extend(extract_lines('function initAddPaymentForm', '  });\n}\n'))
payments_lines.extend(extract_lines('function initEditPaymentModal', '  });\n}\n'))
payments_lines.extend(extract_lines('function initPaymentDeletion', '  });\n}\n'))

documents_lines = []
documents_lines.extend(extract_lines('function initDocumentUploadModal', '  });\n}\n'))
documents_lines.extend(extract_lines('function initDocumentDeletion', '  });\n}\n'))
documents_lines.extend(extract_lines('function initDocumentVerification', '  });\n}\n'))
documents_lines.extend(extract_lines('function initBulkVerification', '  });\n}\n'))

checklist_lines = []
# Vars
vars_lines = extract_lines('const CHECKLIST_REFRESH_INTERVAL_MS', 'let pauseChecklistRefreshUntil = 0;\n')
checklist_lines.extend(vars_lines)
checklist_lines.extend(extract_lines('function pauseChecklistRefresh', '  pauseChecklistRefreshUntil = Math.max(pauseChecklistRefreshUntil, Date.now() + duration);\n}\n'))
checklist_lines.extend(extract_lines('function initChecklistRefresher', '  startInterval();\n}\n'))

email_modal_lines = []
email_modal_lines.extend(extract_lines('function initHoverDropdowns', '  });\n}\n'))
email_modal_lines.extend(extract_lines('function initSendEmailModal', '  });\n}\n'))
email_modal_lines.extend(extract_lines('function initEmailHistoryToggle', '  });\n}\n'))

init_lines = []
init_lines.extend(extract_lines('document.addEventListener(\'DOMContentLoaded\'', '});\n'))

with open(os.path.join(dest_dir, 'ajax.js'), 'w', encoding='utf-8') as f:
    f.writelines(ajax_lines)

with open(os.path.join(dest_dir, 'payments.js'), 'w', encoding='utf-8') as f:
    f.writelines(payments_lines)

with open(os.path.join(dest_dir, 'documents.js'), 'w', encoding='utf-8') as f:
    f.writelines(documents_lines)

with open(os.path.join(dest_dir, 'checklist.js'), 'w', encoding='utf-8') as f:
    f.writelines(checklist_lines)

with open(os.path.join(dest_dir, 'email_modal.js'), 'w', encoding='utf-8') as f:
    f.writelines(email_modal_lines)

with open(os.path.join(dest_dir, 'init.js'), 'w', encoding='utf-8') as f:
    f.writelines(init_lines)

print("Remaining content length:", len(content))
for line in content:
    if line.strip():
        print("Leftover:", line.strip())
