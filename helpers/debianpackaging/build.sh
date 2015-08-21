mkdir build > /dev/null
rm build/a.zip >/dev/null
rm -r build/package>/dev/null
zip -r build/a.zip package/
cd build
pyclean .
rm -r package/usr/lib/kaithem/thirdparty/pytz
unzip a.zip
rm a.zip
chown -R root package
chmod 755 package/usr/bin/kaithem
chmod -R  755 package/usr/lib
chmod -R 755 package/etc
dpkg-deb -b package .
rm -r package
