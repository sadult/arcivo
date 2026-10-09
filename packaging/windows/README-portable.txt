Arcivo – portable edition
=========================

Arcivo.exe            Console home screen: sign in, check connection, proxy settings, sync,
                      sign out. Start here the first time. With arguments it is the full
                      command line, e.g.  Arcivo.exe sync   ·   Arcivo.exe search type:pdf
ArcivoDashboard.exe   The desktop app (dashboard) – browse, search, organise and export.

Because the file "portable.flag" is present, Arcivo stores everything (settings, local
index, cache, logs and the encrypted session) in the "ArcivoData" folder next to the
executables instead of your user profile. Keep this folder private – it contains your
Telegram session. To start fresh, close Arcivo and delete "ArcivoData".

Try without an account:   ArcivoDashboard.exe --demo
Command line help:        Arcivo.exe --help

Telegram blocked on your network? Arcivo.exe → 6 Proxy settings (SOCKS5, HTTP, MTProto),
then 3 Check connection.

Made by Bitologist · https://t.me/Bitologist · https://github.com/sadult/arcivo
Arcivo is an independent, open-source app that uses the Telegram API.
It is not affiliated with or endorsed by Telegram.
