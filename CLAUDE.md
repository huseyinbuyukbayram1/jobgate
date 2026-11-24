# jobgate

Yeni mezunlar için açık kaynak iş arama aracı: ATS panolarından herkese açık ilanları çeker, başvuru engellerini (vize, vatandaşlık, video şartı, deneyim yılı, dil, konum) baştan eler, kalanları CV profiline göre gerekçeli puanlar. Otomatik toplu başvuru HİÇBİR ZAMAN eklenmez; başvuruyu kullanıcı yapar.

Sahibi: Hüseyin Büyükbayram (yeni mezun bilgisayar mühendisi). Repo herkese açık, MIT lisanslı. Konuşma dili Türkçe; kod, commit mesajları, README ve docs İngilizce.

## Çalışma kuralları
- Python 3.12+. Kütüphane API'lerinden emin değilsen Context7 kullan, tahmin etme.
- Önce test, sonra kod (TDD). Testte ağ erişimi yok; kayıtlı yanıtlar (fixture) kullan.
- Küçük, anlamlı commit'ler at (İngilizce, emir kipi). `git push` YAPMA; push'u ben yapacağım. Commit'lere secret, kişisel veri ya da .gitignore'daki hiçbir dosya girmesin.
- Her faz sonunda DUR ve şunları ver: (1) fazda ne yapıldı, (2) kodun kısa anlatımı (mülakatta açıklayabileyim diye: neden bu tasarım, hangi dosya ne yapıyor), (3) PROJECT_LOG.md güncellemesi, (4) İngilizce, kısa, "ne yaptım / hangi sorunla karşılaştım / nasıl çözdüm" tarzında 2 X gönderisi taslağı. Ben onaylamadan sonraki faza geçme.
- Bilmediğin ya da doğrulayamadığın bir şeyi varmış gibi yazma. Uydurma uç nokta, uydurma sayı yok.
- Projeyi AI araçlarıyla geliştirdiğimi README'de açıkça belirt (ne yapıldığı: Claude Code ile geliştirildi, tasarım kararları ve etiketleme bende).

## Gizlilik ve güvenlik (pazarlık yok)
- Repoda yalnızca *.example.* dosyaları bulunur. profile.yaml, *.db, .env, cv/ .gitignore'da kalır.
- Örnek profil uydurma bir kişiye aittir. Gerçek ad, e-posta, telefon, başvuru geçmişi, CV içeriği hiçbir dosyada, test verisinde ya da çıktıda yer almaz.
- Sahibin mevcut ya da geçmiş hiçbir işvereni/kurumuyla ilgili kod, veri, ad ya da ayrıntı repoya ya da metinlere girmez (kurum adı yerel hafızada tutulur, repoda yazılmaz).
- Başvurduğum şirketleri ve işverenleri eşleştiren veri repoya girmez. companies.example.yaml için herkese açık, tarafsız bir liste kullan.
- pre-commit ile gizli anahtar taraması (gitleaks ya da eşdeğeri) kur.
- Gizli anahtarı koda, loga ya da çıktıya yazma. İzin atlama bayrağı kullanma. "curl | bash" tarzı kurulum adımı ekleme.

## Veri kaynakları ve davranış kuralları
- Yalnızca Greenhouse, Lever ve Ashby'nin herkese açık, kimlik doğrulamasız ilan uç noktaları. HTML kazıma, giriş gerektiren sayfa, bot engeli aşma YOK.
- Uç nokta biçimleri hafızadandır: önce her birini 3 gerçek şirketle elle dene ve resmi dokümanla doğrula; farklıysa dokümana uy ve docs/sources.md'ye yaz.
- Açık User-Agent (repo adresini içersin), istekler arası gecikme, zaman aşımı, en fazla 3 yeniden deneme (artan bekleme), yerel yanıt önbelleği (aynı gece aynı uç noktaya iki kez gitme).
- Bir şirket çökerse hatayı kaydet, hat devam etsin.
- Her ATS'nin kullanım şartı bağlantısı README'de; şartlar değişirse kaynak kapatılabilmeli (yapılandırmadan).

## Mimari (5 aşama, her biri bağımsız test edilebilir)
1. Fetch: ATS başına adapter, ortak arayüz.
2. Normalize: ham JSON -> tek Job şeması (şirket, rol, konum, açıklama, link, tarih, ats, ats_job_id).
3. Filter: kural tabanlı engel filtresi; her karar bir neden koduyla gelir. Kesin engel = ele, belirsiz/çakışan ifade = "kontrol et".
4. Score: 0-100 açıklanabilir puan. Rol/unvan 30, teknoloji 20-30 (ağırlıklar yapılandırmada), seviye 20, konum/çalışma biçimi 10, ücret sinyali 10. Rapor "72: rol 28, teknoloji 20, seviye 16, konum 8" biçiminde gösterir. Ağırlıklar YAML'dedir.
5. Store + Report: SQLite, yinelenen ilanları eleme, durum geçmişi (bulundu / başvuruldu / elendi), Markdown ve CSV rapor.

Teknoloji: httpx, pydantic v2, typer, PyYAML, pytest, ruff, SQLite (stdlib sqlite3), GitHub Actions CI. LLM: Ollama (yerel) isteğe bağlı; bulut API seçeneği yapılandırmayla, anahtar zorunlu değil.

Temel kural: karar her zaman kural tabanlıdır. LLM yalnızca puan gerekçesinin metnini zenginleştirir, hiçbir eleme ya da puan kararını değiştirmez. LLM kapalıyken her şey çalışır (bunun testi var).

## Repo yapısı
src/jobgate/{adapters/{greenhouse,lever,ashby}.py, models.py, filters.py, scoring.py, storage.py, report.py, llm.py, cli.py}
tests/ (fixtures/ ve etiketli ilan seti), docs/ (sources.md, architecture.md), companies.example.yaml, profile.example.yaml, README.md, CHANGELOG.md, PROJECT_LOG.md, LICENSE

## Engel filtreleri (profile.yaml'dan beslenir)
Vize/çalışma izni gerçekten gerekli -> ele (kullanıcının ülke profiline göre) | Vatandaşlık/güvenlik izni -> ele | Video/ödev şartı -> ele (kullanıcı ayarı) | Deneyim yılı eşiği aşıyorsa -> ele | Konum/saat dilimi profil dışıysa -> ele | Gerekli dil profilde yoksa -> ele | "we sponsor" ile "no sponsorship" gibi çakışan ifade -> kontrol et. Her kural için en az bir geçen ve bir elenen test örneği, her karar için neden kodu.

Etiketli test seti: 40 ilan (engelli / engelsiz / belirsiz). Repoya tam ilan metni koyma; yalnızca kuralın ilgili cümlelerini kısa alıntı olarak kaynak bağlantısıyla sakla (ya da sentetik yaz). Etiketleri ben doğrularım: sen aday ilanları ve önerilen etiketi CSV olarak hazırla; "human_verified" alanı yalnızca ben onaylayınca true olur. Doğruluk hedefi: doğrulanmış sette en az %90, yanlış eleme oranı raporda ayrıca gösterilir.

## Bekleyen kapı (zorunlu)
Etiketler ben `human_verified=true` yapana ve değerlendirme yeniden çalışana kadar README'ye, X gönderilerine, sürüm notlarına ya da herhangi bir herkese açık yere DOĞRULUK SAYISI yazma ve v0.1.0 etiketini açma. Ayrıntı: PROJECT_LOG.md başındaki "PENDING GATES".

## Komutlar
jobgate fetch | filter | score | report | mark <id> <durum> | run (hepsini sırayla) | companies validate. Aynı komutu iki kez çalıştırmak yinelenen kayıt üretmemeli (test var). Hata mesajları ve --help metinleri açık ve İngilizce olmalı.

## Fazlar (hepsi yapılacak; faz sonunda dur, yukarıdaki kurala bak)
Faz 0: iskelet, CI (pytest + ruff), pre-commit gizli anahtar taraması, README iskeleti.
Faz 1: Job şeması, 3 adapter, önbellek/yeniden deneme/gecikme, companies okuyucusu (10 örnek şirket), fixture testleri. Kapı: 30 şirketten çekim, biri çökse devam.
Faz 2: profile şeması ve örneği, filtre kuralları, etiketli set, %90+ doğruluk. Kapı: doğruluk ve yanlış eleme oranı raporda.
Faz 3: puanlama (YAML ağırlık), SQLite şeması, komutlar, Markdown/CSV rapor, iki kez çalıştırma testi. Kapı: tek komutla gerçek ilanlarla sıralı rapor.
Faz 4: Ollama ile kısa gerekçe, LLM-kapalı testi, README (problem, 10 dakikalık kurulum, örnek çıktı, mermaid mimari şeması, sınırlamalar, "ne yapmıyor": otomatik başvuru yok, yol haritası), CHANGELOG. Kapı: README'den 10 dakikada ilk rapor.
v0.1.0 etiketini (tag) yalnızca ben açıkça söylersem oluştur.

## Kapsam dışı (ekleme, önermeden önce bana sor)
Web arayüzü, hesap sistemi, bildirimler, başka ilan kaynakları, otomatik başvuru (asla).
