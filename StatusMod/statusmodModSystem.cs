using Vintagestory.API.Common;
using Vintagestory.API.Server;
using System.Net;
using Newtonsoft.Json;
using Vintagestory.GameContent;
using System.Text;
using System.Linq;
using System;
using System.Threading;
using System.Net.Http;
using System.Threading.Tasks;

namespace StatusMod
{
    public class StatusModSystem : ModSystem, IDisposable
    {
        private ICoreServerAPI api;
        private HttpListener listener;
        private const string Url = "http://localhost:8080/status/";
        private readonly object _lock = new object();
        private readonly CancellationTokenSource _cts = new CancellationTokenSource();
        private ILogger _logger;
        private bool _disposed = false;
        private long _gameTickListenerId;
        private long _stormCheckTickListenerId;
        private long _seasonCheckTickListenerId;
        
        // Время ожидания запроса в миллисекундах
        private const int RequestTimeoutMs = 100;
        
        // Статус шторма для отслеживания изменений
        private bool _lastStormStatus = false;
        private bool _stormWarningIssued = false;
        
        // Статус сезона для отслеживания изменений
        private string _lastSeason = "";
        
        // Добавляем информацию о шторме
        private class StormForecast
        {
            public bool IsActive { get; set; }
            public string Message { get; set; }
            public bool IsWarning { get; set; }
        }
        
        // Класс для сезонных уведомлений
        private class SeasonNotification
        {
            public string Message { get; set; }
            public string Season { get; set; }
            public bool IsNewSeason { get; set; }
        }

        private const string DiscordBotUrl = "http://localhost:8081/status/notification";

        // Статический HttpClient для многократного использования
        private static readonly HttpClient httpClient = new HttpClient();

        public override void StartServerSide(ICoreServerAPI api)
        {
            this.api = api ?? throw new ArgumentNullException(nameof(api));
            this._logger = api.Logger;
            
            // Регистрируем обработчик события выгрузки сервера
            api.Event.ServerRunPhase(EnumServerRunPhase.Shutdown, () => Dispose());
            
            try
            {
                if (!IsPortAvailable(8080))
                {
                    _logger.Error("Порт 8080 уже используется!");
                    return;
                }

                _logger.Event("Запущен HTTP сервер для статуса на адресе " + Url);
                StartHttpServer();
                
                // Запускаем проверку шторма каждые 5 секунд
                _stormCheckTickListenerId = api.Event.RegisterGameTickListener(CheckTemporalStorm, 5000);
                
                // Запускаем проверку сезона каждую 1 минуту
                _seasonCheckTickListenerId = api.Event.RegisterGameTickListener(CheckSeasonChange, 60000);
                
                // Получаем и сохраняем текущий сезон при запуске
                _lastSeason = GetCurrentSeason();
                _logger.Event($"Запущено отслеживание сезонов. Текущий сезон: {_lastSeason}");
            }
            catch (Exception ex)
            {
                _logger.Error($"Не удалось запустить HTTP сервер: {ex}");
            }
        }

        private void StartHttpServer()
        {
            try
            {
                listener = new HttpListener();
                listener.Prefixes.Add(Url);
                listener.Start();
                
                _logger.Event("HTTP сервер успешно запущен на " + Url);
                
                // Инициируем первый асинхронный запрос
                listener.BeginGetContext(OnRequestReceived, listener);
                
                // Также регистрируем тик только для проверки состояния
                _gameTickListenerId = (long)api.Event.RegisterGameTickListener(CheckServerStatus, 60000);
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при запуске HTTP-сервера: {ex}");
            }
        }

        private void HandleHttpRequests(float dt)
        {
            if (_disposed || !listener.IsListening) return;

            // Вместо запуска нового потока для каждого запроса, проверим наличие запросов асинхронно
            try {
                IAsyncResult result = listener.BeginGetContext(OnRequestReceived, listener);
            }
            catch (Exception ex) {
                _logger?.Error($"Ошибка при начале прослушивания запросов: {ex}");
            }
        }

        private void OnRequestReceived(IAsyncResult result)
        {
            if (_disposed) return;

            HttpListenerResponse response = null;
            try
            {
                var listener = (HttpListener)result.AsyncState;
                if (!listener.IsListening) return;

                HttpListenerContext context = listener.EndGetContext(result);
                response = context.Response;

                // Убираем лишнее логирование
                // _logger.Event($"Получен запрос от {context.Request.RemoteEndPoint}");

                // Снова начинаем прослушивать для следующего запроса
                listener.BeginGetContext(OnRequestReceived, listener);

                // Готовим данные ответа
                var serverData = new
                {
                    playerCount = api.World.AllOnlinePlayers?.Length ?? 0,
                    players = api.World.AllOnlinePlayers?.Select(p => p.PlayerName).ToArray() ?? new string[0],
                    time = api.World.Calendar.PrettyDate(),
                    temporalStorm = GetTemporalStormStatus() ? "Активен" : "Неактивен"
                };

                string jsonResponse = JsonConvert.SerializeObject(serverData);
                byte[] buffer = Encoding.UTF8.GetBytes(jsonResponse);

                response.ContentType = "application/json";
                response.ContentLength64 = buffer.Length;
                response.AddHeader("Access-Control-Allow-Origin", "*");
                response.AddHeader("Cache-Control", "no-cache, no-store, must-revalidate");
                
                // Запись ответа максимально быстро
                try {
                    response.OutputStream.Write(buffer, 0, buffer.Length);
                    // Убираем лишнее логирование
                    // _logger.Event($"Отправлен ответ: {jsonResponse}");
                }
                catch (Exception ex) {
                    _logger.Error($"Ошибка при отправке ответа: {ex}");
                }
                finally {
                    try { response?.Close(); } catch { }
                }
            }
            catch (HttpListenerException ex)
            {
                _logger.Error($"Ошибка HttpListener: {ex}");
            }
            catch (Exception ex)
            {
                _logger?.Error($"Ошибка при обработке запроса: {ex}");
            }
            finally
            {
                try { response?.Close(); } catch { }
            }
        }

        private bool GetTemporalStormStatus()
        {
            if (_disposed || api == null) return false;
            
            try {
                var systems = api.ModLoader.GetModSystem<SystemTemporalStability>();
                if (systems?.StormData != null)
                {
                    return systems.StormData.nowStormActive;
                }
            }
            catch {
                // Игнорируем ошибки при получении статуса шторма
            }
            return false;
        }

        public override void Dispose()
        {
            // Защита от повторного вызова
            if (_disposed) return;
            _disposed = true;
            
            try
            {
                if (_cts != null && !_cts.IsCancellationRequested)
                {
                    _cts.Cancel();
                }
                
                if (api != null)
                {
                    try
                    {
                        api.Event.UnregisterGameTickListener(_gameTickListenerId);
                        api.Event.UnregisterGameTickListener(_stormCheckTickListenerId);
                        api.Event.UnregisterGameTickListener(_seasonCheckTickListenerId);
                    }
                    catch (Exception ex)
                    {
                        _logger?.Error($"Ошибка при отмене регистрации обработчика игровых тиков: {ex}");
                    }
                }
                
                lock (_lock)
                {
                    if (listener != null)
                    {
                        try
                        {
                            if (listener.IsListening)
                            {
                                listener.Stop();
                            }
                            listener.Close();
                        }
                        catch (Exception ex)
                        {
                            _logger?.Error($"Ошибка при закрытии HTTP слушателя: {ex}");
                        }
                        finally
                        {
                            listener = null;
                        }
                    }
                }
                
                if (_cts != null)
                {
                    try
                    {
                        _cts.Dispose();
                    }
                    catch (Exception ex)
                    {
                        _logger?.Error($"Ошибка при освобождении ресурсов токена отмены: {ex}");
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Error($"Ошибка в методе Dispose: {ex}");
            }
            finally
            {
                try 
                { 
                    // Вызываем базовую реализацию
                    base.Dispose(); 
                } 
                catch (Exception ex) 
                {
                    _logger?.Error($"Ошибка в базовом методе Dispose: {ex}");
                }
            }
        }

        private bool IsPortAvailable(int port)
        {
            try
            {
                using (var testListener = new HttpListener())
                {
                    testListener.Prefixes.Add($"http://localhost:{port}/");
                    try
                    {
                        testListener.Start();
                        return true;
                    }
                    catch (HttpListenerException)
                    {
                        return false;
                    }
                }
            }
            catch
            {
                return false;
            }
        }

        private void CheckServerStatus(float dt)
        {
            // Этот метод просто периодически проверяет, что сервер работает
            if (_disposed) return;
            
            if (listener == null || !listener.IsListening)
            {
                _logger.Warning("HTTP сервер не отвечает, пробуем перезапустить");
                try
                {
                    if (listener != null)
                    {
                        try { listener.Stop(); } catch { }
                        try { listener.Close(); } catch { }
                    }
                    
                    StartHttpServer();
                }
                catch (Exception ex)
                {
                    _logger.Error($"Ошибка при перезапуске HTTP сервера: {ex}");
                }
            }
        }
        
        private void CheckTemporalStorm(float dt)
        {
            try
            {
                // Получаем текущее состояние шторма
                bool currentStormStatus = GetTemporalStormStatus();
                
                // Получаем данные о штормах
                var systems = api.ModLoader.GetModSystem<SystemTemporalStability>();
                
                if (systems?.StormData != null)
                {
                    var stormData = systems.StormData;
                    
                    // Варианты предупреждений о шторме
                    var stormWarningMessages = new string[]
                    {
                        "⚠️ **ВНИМАНИЕ**: Временные разломы расширяются! Скоро начнется темпоральный шторм! Приготовьтесь к искажениям реальности!",
                        "🌩️ **ПРЕДУПРЕЖДЕНИЕ**: Детекторы темпоральных колебаний зафиксировали приближение шторма! Спрячьте ценные руды в подвалах!",
                        "⏰ **ТРЕВОГА**: Надвигается темпоральная буря! Укройте животных и соберите инструменты с поверхности!",
                        "🔮 **ПРЕДВЕСТИЕ**: Странные искажения в пространстве указывают на приближение шторма! Заприте ценные реликвии в сундуки!",
                        "⚡ **ОПОВЕЩЕНИЕ**: Энергия временного шторма приближается! Расставьте защитные обереги вокруг жилища!"
                    };
                    
                    // Варианты сообщений о начале шторма
                    var stormStartMessages = new string[]
                    {
                        "🌩️ **ТЕМПОРАЛЬНЫЙ ШТОРМ НАЧАЛСЯ**! Укройтесь в глубоких подвалах или пещерах!",
                        "💥 **БУРЯ ОБРУШИЛАСЬ НА МИР**! Временные аномалии искажают пространство! Держитесь подальше от поверхности!",
                        "⚡ **ШТОРМ В РАЗГАРЕ**! Временные сущности появляются повсюду! Оставайтесь в укрытии!",
                        "🌀 **ВНИМАНИЕ: ШТОРМ АКТИВЕН**! Дикие животные в панике, руда нестабильна! Не покидайте убежище!",
                        "🔥 **РАЗРУШИТЕЛЬНАЯ БУРЯ НАЧАЛАСЬ**! Мир искажается под напором временной энергии! Сохраняйте спокойствие!"
                    };
                    
                    // Варианты сообщений об окончании шторма
                    var stormEndMessages = new string[]
                    {
                        "✨ **Темпоральный шторм закончился**. Проверьте свои постройки на наличие повреждений.",
                        "🌈 **Буря утихла**. Осмотрите окрестности на наличие временных артефактов и редких ресурсов.",
                        "🌞 **Конец шторма**! Восстановите поврежденные структуры и соберите выпавшие фрагменты времени.",
                        "🌅 **Буря отступила**. Самое время выйти на поверхность и оценить изменения в ландшафте.",
                        "🍃 **Шторм рассеялся**. Проверьте сохранность запасов и приведите в порядок мастерские."
                    };

                    // Генератор случайных чисел
                    var random = new Random();
                    
                    // Если приближается шторм и предупреждение еще не было отправлено
                    if (!currentStormStatus && !_stormWarningIssued && stormData.nextStormTotalDays - api.World.Calendar.TotalDays < 0.25)
                    {
                        _stormWarningIssued = true;
                        string message = stormWarningMessages[random.Next(stormWarningMessages.Length)];
                        SendDiscordNotification(new StormForecast { IsActive = false, Message = message, IsWarning = true });
                        _logger.Event("Отправлено предупреждение о шторме");
                    }
                    
                    // Если шторм только что начался
                    if (currentStormStatus && !_lastStormStatus)
                    {
                        string message = stormStartMessages[random.Next(stormStartMessages.Length)];
                        SendDiscordNotification(new StormForecast { IsActive = true, Message = message, IsWarning = false });
                        _logger.Event("Отправлено уведомление о начале шторма");
                    }
                    
                    // Если шторм только что закончился
                    if (!currentStormStatus && _lastStormStatus)
                    {
                        _stormWarningIssued = false; // Сбрасываем флаг предупреждения
                        string message = stormEndMessages[random.Next(stormEndMessages.Length)];
                        SendDiscordNotification(new StormForecast { IsActive = false, Message = message, IsWarning = false });
                        _logger.Event("Отправлено уведомление об окончании шторма");
                    }
                    
                    // Обновляем последнее известное состояние шторма
                    _lastStormStatus = currentStormStatus;
                }
            }
            catch (Exception ex)
            {
                _logger?.Error($"Ошибка при проверке темпорального шторма: {ex}");
            }
        }
        
        private void SendDiscordNotification(StormForecast forecast)
        {
            try
            {
                // Формируем JSON-запрос
                var requestData = new
                {
                    type = "storm_notification",
                    is_active = forecast.IsActive,
                    message = forecast.Message,
                    is_warning = forecast.IsWarning
                };

                string jsonData = JsonConvert.SerializeObject(requestData);
                StringContent content = new StringContent(jsonData, Encoding.UTF8, "application/json");

                // Создаем асинхронный запрос
                Task.Run(async () =>
                {
                    try
                    {
                        var response = await httpClient.PostAsync(DiscordBotUrl, content);
                        response.EnsureSuccessStatusCode();
                        _logger.Event($"Уведомление о шторме успешно отправлено");
                    }
                    catch (Exception ex)
                    {
                        _logger.Error($"Ошибка при отправке уведомления о шторме: {ex.Message}");
                    }
                });
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при формировании уведомления о шторме: {ex.Message}");
            }
        }
        
        private void CheckSeasonChange(float dt)
        {
            try
            {
                string currentSeason = GetCurrentSeason();
                
                // Если сезон определен и отличается от предыдущего
                if (!string.IsNullOrEmpty(currentSeason) && currentSeason != "Unknown" && _lastSeason != string.Empty && _lastSeason != currentSeason)
                {
                    // Формируем тематическое сообщение для текущего сезона
                    string message = GetSeasonalMessage(currentSeason);
                    
                    _logger.Event($"Смена сезона: {_lastSeason} -> {currentSeason}");
                    
                    // Отправляем уведомление в Discord
                    SendSeasonNotification(new SeasonNotification { 
                        Season = currentSeason, 
                        Message = message,
                        IsNewSeason = true 
                    });
                    
                    // Обновляем значение последнего сезона
                    _lastSeason = currentSeason;
                }
                else if (currentSeason != "Unknown" && _lastSeason != currentSeason)
                {
                    // Обновляем последний сезон без отправки уведомления (для первой инициализации)
                    _lastSeason = currentSeason;
                }
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при проверке смены сезона: {ex}");
            }
        }
        
        private string GetCurrentSeason()
        {
            try
            {
                if (api?.World?.Calendar != null)
                {
                    // Получаем полную строку даты (например: "9 мая 2 года, 08:44")
                    string prettyDate = api.World.Calendar.PrettyDate();
                    
                    // Извлекаем месяц из строки даты
                    string[] dateParts = prettyDate.Split(' ');
                    if (dateParts.Length >= 2)
                    {
                        string month = dateParts[1].ToLowerInvariant();
                        
                        // Определяем сезон на основе месяца
                        string season = GetSeasonByMonth(month);
                        
                        return season;
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Error($"Ошибка при получении текущего сезона: {ex}");
            }
            
            return string.Empty;
        }
        
        private string GetSeasonByMonth(string month)
        {
            // Обрезаем окончания и запятые
            month = month.TrimEnd(',', '.').ToLowerInvariant();
            
            // Весна: март, апрель, май
            if (month.StartsWith("март") || month.StartsWith("апрел") || month.StartsWith("мая") || month == "май")
                return "Spring";
            
            // Лето: июнь, июль, август
            if (month.StartsWith("июн") || month.StartsWith("июл") || month.StartsWith("август"))
                return "Summer";
            
            // Осень: сентябрь, октябрь, ноябрь
            if (month.StartsWith("сентябр") || month.StartsWith("октябр") || month.StartsWith("ноябр"))
                return "Autumn";
            
            // Зима: декабрь, январь, февраль
            if (month.StartsWith("декабр") || month.StartsWith("январ") || month.StartsWith("феврал"))
                return "Winter";
            
            // Если не удалось определить сезон, выводим отладочную информацию
            _logger.Warning($"Не удалось определить сезон для месяца: '{month}'");
            return "Unknown";
        }
        
        private string GetSeasonalMessage(string season)
        {
            // Словарь с вариантами сообщений для каждого сезона
            var springMessages = new string[]
            {
                "🌱🌷 **Наступила Весна!** 🌸\nПрирода пробуждается от зимнего сна. Время посадить первые растения и подготовиться к новому году!",
                "🌼🌿 **Весна пришла в земли Vintage Story!** 🦋\nТает снег, распускаются первые цветы, и мир наполняется красками после долгой зимы.",
                "🌱☔ **Наступил сезон весны!** 🌈\nВремя дождей и новой жизни. Соберите семена и начните подготовку ваших полей!",
                "🐝🌷 **Весенний сезон начался!** 🍀\nПчелы возвращаются, деревья цветут. Отличное время для постройки ульев и сбора первых трав!",
                "🌄🌻 **Весна вступила в свои права!** 💐\nДни становятся длиннее, а ночи теплее. Идеальное время для засева полей и приручения диких животных!"
            };
            
            var summerMessages = new string[]
            {
                "🌞🌾 **Наступило Лето!** 🌻\nСамое теплое время года принесло богатый урожай и длинные дни. Используйте это время для торговли и путешествий!",
                "🍓🌿 **Летний сезон в разгаре!** 🥤\nЖаркие дни, теплые ночи и изобилие плодов. Самое время для сбора дикорастущих растений и строительства!",
                "🌅🍯 **Пришло лето в Vintage Story!** 🧵\nДлинные дни позволяют заниматься ремеслом дольше. Соберите мед, травы и материалы для ремесла!",
                "🦗🌱 **Летний зной охватил мир!** 🌡️\nВремя изобилия и светлых ночей. Наполните погреба и кладовые, готовьтесь к грядущей осени!",
                "🐝🥖 **Лето вступило в свои права!** 🌿\nСозревает урожай, цветут медоносы. Идеальное время для развития пасеки и сбора урожая!"
            };
            
            var autumnMessages = new string[]
            {
                "🍂🍁 **Наступила Осень!** 🌰\nДеревья окрасились в золотые цвета, а животные готовятся к холодам. Пора собирать последний урожай и запасаться топливом на зиму!",
                "🍄🦊 **Осенний сезон начался!** 🍂\nЛистья меняют цвет, грибы покрывают лесные поляны. Время заготовок и ремонта жилищ перед холодами!",
                "🌧️🍎 **Осень пришла в мир Vintage Story!** 🧣\nДни становятся короче, ночи холоднее. Проверьте ваши запасы еды и почините инструменты!",
                "🍁🦔 **Золотая осень окутала мир!** 🥮\nПоследний шанс добыть руду и собрать урожай перед наступлением суровой зимы.",
                "🌫️🌾 **Осеннее время настало!** 🏺\nТуманные утра, прохладные вечера. Самое время для заготовки солений и вяления мяса!"
            };
            
            var winterMessages = new string[]
            {
                "❄️☃️ **Наступила Зима!** 🌨️\nСуровые морозы и долгие ночи ждут вас. Запасы дров и еды должны быть готовы, носите тёплую одежду!",
                "🧊🧥 **Зимний сезон пришел!** ⛄\nСнег покрыл землю, реки замерзли. Время кузнечного дела и изготовления тёплой одежды!",
                "🌬️❄️ **Зима охватила мир Vintage Story!** 🏔️\nСамое суровое время года проверит вашу готовность. Используйте погреба для сохранения припасов!",
                "🧣🧤 **Началась зимняя стужа!** 🧪\nВремя алхимии, чтения и улучшения мастерских. Добывайте редкие руды глубоко под землей!",
                "🪵🔥 **Холодная зима вступила в свои права!** ☕\nПоддерживайте огонь в печи и проверьте запасы дров. Хороший момент для улучшения вашего жилища!"
            };
            
            // Генератор случайных чисел
            var random = new Random();
            
            switch (season.ToLowerInvariant())
            {
                case "spring":
                    return springMessages[random.Next(springMessages.Length)];
                
                case "summer":
                    return summerMessages[random.Next(summerMessages.Length)];
                
                case "autumn":
                case "fall":
                    return autumnMessages[random.Next(autumnMessages.Length)];
                
                case "winter":
                    return winterMessages[random.Next(winterMessages.Length)];
                
                default:
                    return $"🌍 **Смена сезона!** Наступил новый сезон: {season}";
            }
        }
        
        private void SendSeasonNotification(SeasonNotification notification)
        {
            try
            {
                // Формируем JSON-запрос
                var requestData = new
                {
                    type = "season_notification",
                    season = notification.Season.ToLowerInvariant(),
                    message = notification.Message,
                    is_new_season = notification.IsNewSeason
                };

                string jsonData = JsonConvert.SerializeObject(requestData);
                StringContent content = new StringContent(jsonData, Encoding.UTF8, "application/json");

                // Создаем асинхронный запрос
                Task.Run(async () =>
                {
                    try
                    {
                        var response = await httpClient.PostAsync(DiscordBotUrl, content);
                        response.EnsureSuccessStatusCode();
                        _logger.Event($"Уведомление о смене сезона успешно отправлено");
                    }
                    catch (Exception ex)
                    {
                        _logger.Error($"Ошибка при отправке уведомления о смене сезона: {ex.Message}");
                    }
                });
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при формировании уведомления о смене сезона: {ex.Message}");
            }
        }
    }
}
