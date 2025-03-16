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
using System.Collections.Generic;

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
        private long _playerCountCheckListenerId;
        
        // Флаг инициализации мода
        private bool _isInitialized = false;
        
        // Новый таймер для отправки буферизованных уведомлений
        private long _notificationSenderTickListenerId;
        
        // Счетчик для периодического обновления статуса сервера
        private float _periodicUpdateCounter = 0;
        
        // Статус количества игроков для отслеживания
        private int _lastPlayerCount = 0;
        private bool _lastServerOnline = false;
        
        // Время ожидания запроса в миллисекундах
        private const int RequestTimeoutMs = 100;
        
        // Статус шторма для отслеживания изменений
        private bool _lastStormStatus = false;
        private bool _stormWarningIssued = false;
        
        // Статус сезона для отслеживания изменений
        private string _lastSeason = "";
        
        // Буфер для хранения уведомлений, которые нужно отправить
        private List<NotificationItem> _notificationBuffer = new List<NotificationItem>();
        
        // Объект для синхронизации доступа к буферу
        private readonly object _bufferLock = new object();
        
        // Интервал отправки уведомлений (в секундах)
        private const float NotificationSendInterval = 15.0f;
        
        // Счетчик времени для отправки уведомлений
        private float _notificationSendCounter = 0;
        
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
        
        // Класс для уведомлений о статусе сервера
        private class ServerStatusNotification
        {
            public bool IsOnline { get; set; }
            public int PlayerCount { get; set; }
            public string Message { get; set; }
            public string[] Players { get; set; }
        }

        private const string DiscordBotUrl = "http://localhost:8081/status/notification";

        // Статический HttpClient для многократного использования
        private static readonly HttpClient httpClient = new HttpClient();

        // Класс для хранения элементов буфера уведомлений
        private class NotificationItem
        {
            public object Data { get; set; }
            public string Type { get; set; }
            public DateTime TimeAdded { get; set; }
            
            public NotificationItem(object data, string type)
            {
                Data = data;
                Type = type;
                TimeAdded = DateTime.Now;
            }
        }

        // Новый таймер для периодической отправки статуса сервера
        private long _periodicStatusTickListenerId;

        public override void StartServerSide(ICoreServerAPI api)
        {
            try
            {
                _logger = api.Logger;
                _logger.Warning("Инициализация мода StatusMod");
                
                this.api = api;
                
                _gameTickListenerId = api.Event.RegisterGameTickListener(HandleHttpRequests, 1000);
                _stormCheckTickListenerId = api.Event.RegisterGameTickListener(dt => CheckTemporalStormInternal(), 2000);
                _seasonCheckTickListenerId = api.Event.RegisterGameTickListener(dt => CheckSeasonChangeInternal(), 10000);
                _playerCountCheckListenerId = api.Event.RegisterGameTickListener(dt => CheckPlayerCountInternal(), 5000);
                _notificationSenderTickListenerId = api.Event.RegisterGameTickListener(ProcessNotificationBuffer, 1000);
                _periodicStatusTickListenerId = api.Event.RegisterGameTickListener(SendPeriodicServerStatus, 20000);
                
                StartHttpServer();
                
                api.Event.PlayerJoin += OnPlayerJoin;
                api.Event.PlayerDisconnect += OnPlayerDisconnect;
                
                SendInitialServerStatus();
                
                // Отмечаем, что мод полностью инициализирован
                _isInitialized = true;
                
                _logger.Warning("Мод StatusMod успешно инициализирован");
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при инициализации мода StatusMod: {ex}");
            }
        }

        private void StartHttpServer()
        {
            try
            {
                listener = new HttpListener();
                listener.Prefixes.Add(Url);
                listener.Start();
                
                _logger.Warning("HTTP сервер успешно запущен на " + Url);
                
                listener.BeginGetContext(OnRequestReceived, listener);
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

                // Снова начинаем прослушивать для следующего запроса
                listener.BeginGetContext(OnRequestReceived, listener);
                
                // Проверяем, инициализирован ли мод полностью
                if (!_isInitialized)
                {
                    // Получаем максимальное количество игроков из конфигурации, если возможно
                    int defaultMaxPlayers = 0;
                    try {
                        defaultMaxPlayers = api?.Server?.Config?.MaxClients ?? 0;
                    } catch {
                        defaultMaxPlayers = 0;
                    }
                    
                    // Если не удалось получить, используем стандартное значение
                    if (defaultMaxPlayers <= 0) {
                        defaultMaxPlayers = 32;
                    }
                    
                    // Если мод еще не инициализирован, возвращаем базовое информационное сообщение
                    var initData = new
                    {
                        online = false,
                        playerCount = 0,
                        maxPlayers = defaultMaxPlayers,
                        players = new string[0],
                        prettyDate = "Сервер запускается...",
                        temporalStorm = "Неактивен",
                        status = "initializing"
                    };
                    
                    string initResponse = JsonConvert.SerializeObject(initData);
                    byte[] initBuffer = Encoding.UTF8.GetBytes(initResponse);
                    
                    // Устанавливаем правильные заголовки
                    response.StatusCode = 200;
                    response.ContentType = "application/json; charset=utf-8";
                    response.ContentLength64 = initBuffer.Length;
                    response.AddHeader("Access-Control-Allow-Origin", "*");
                    response.AddHeader("Cache-Control", "no-cache, no-store, must-revalidate");
                    response.AddHeader("Pragma", "no-cache");
                    response.AddHeader("Expires", "0");
                    
                    response.OutputStream.Write(initBuffer, 0, initBuffer.Length);
                    response.Close();
                    return;
                }

                // Готовим данные ответа
                bool isOnline = true; // Сервер считается онлайн, если код выполняется
                int playerCount = 0;
                int maxPlayers = 0; // Начальное значение
                string[] playerNames = new string[0];
                
                try {
                    playerCount = api.World.AllOnlinePlayers?.Length ?? 0;
                    playerNames = api.World.AllOnlinePlayers?.Select(p => p.PlayerName).ToArray() ?? new string[0];
                    
                    // Если не можем получить количество игроков напрямую, но у нас есть их имена, 
                    // используем количество элементов в массиве
                    if (playerCount == 0 && playerNames.Length > 0) {
                        playerCount = playerNames.Length;
                    }
                    
                    // Получаем максимальное количество игроков из конфигурации
                    maxPlayers = api.Server.Config.MaxClients;
                } catch (Exception ex) {
                    _logger?.Warning($"Ошибка при получении данных о игроках: {ex.Message}");
                }
                
                // Если не удалось получить максимальное число игроков, используем стандартное значение
                if (maxPlayers <= 0) {
                    maxPlayers = 32; // Стандартное значение
                }
                
                var serverData = new
                {
                    online = isOnline,
                    playerCount = playerCount,
                    maxPlayers = maxPlayers,
                    players = playerNames,
                    prettyDate = api.World.Calendar.PrettyDate(),
                    temporalStorm = GetTemporalStormStatus() ? "Активен" : "Неактивен"
                };

                string jsonResponse = JsonConvert.SerializeObject(serverData);
                byte[] buffer = Encoding.UTF8.GetBytes(jsonResponse);

                // Устанавливаем правильные заголовки
                response.StatusCode = 200;
                response.ContentType = "application/json; charset=utf-8";
                response.ContentLength64 = buffer.Length;
                response.AddHeader("Access-Control-Allow-Origin", "*");
                response.AddHeader("Cache-Control", "no-cache, no-store, must-revalidate");
                response.AddHeader("Pragma", "no-cache");
                response.AddHeader("Expires", "0");
                
                try {
                    response.OutputStream.Write(buffer, 0, buffer.Length);
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
                        api.Event.UnregisterGameTickListener(_playerCountCheckListenerId);
                        
                        // Отменяем регистрацию таймера для отправки уведомлений
                        api.Event.UnregisterGameTickListener(_notificationSenderTickListenerId);
                        
                        // Отменяем регистрацию таймера для периодической отправки статуса
                        api.Event.UnregisterGameTickListener(_periodicStatusTickListenerId);
                        
                        // Отправляем оставшиеся уведомления в буфере
                        lock (_bufferLock)
                        {
                            if (_notificationBuffer.Count > 0)
                            {
                                _logger?.Warning($"Отправка оставшихся {_notificationBuffer.Count} уведомлений перед выгрузкой мода");
                                
                                // Создаем пакет с уведомлениями
                                var batchRequest = new
                                {
                                    type = "notification_batch",
                                    timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"),
                                    notifications = _notificationBuffer.Select(n => new
                                    {
                                        type = n.Type,
                                        data = n.Data,
                                        timestamp = n.TimeAdded.ToString("yyyy-MM-dd HH:mm:ss")
                                    }).ToArray()
                                };
                                
                                // Отправляем пакет уведомлений синхронно
                                try
                                {
                                    string jsonString = JsonConvert.SerializeObject(batchRequest);
                                    var content = new StringContent(jsonString, Encoding.UTF8, "application/json");
                                    var response = httpClient.PostAsync(DiscordBotUrl, content).Result;
                                    
                                    if (response.IsSuccessStatusCode)
                                    {
                                        // Убираем логирование успешных отправок
                                        // _logger?.Warning("Оставшиеся уведомления успешно отправлены");
                                    }
                                    else
                                    {
                                        _logger?.Warning($"Ошибка отправки оставшихся уведомлений: {response.StatusCode}");
                                    }
                                }
                                catch (Exception ex)
                                {
                                    _logger?.Error($"Ошибка при отправке оставшихся уведомлений: {ex.Message}");
                                }
                                
                                // Очищаем буфер
                                _notificationBuffer.Clear();
                            }
                        }
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
            
            try
            {
                if (listener == null || !listener.IsListening)
                {
                    _logger.Warning("HTTP сервер не отвечает, пробуем перезапустить");
                    SafeRestartHttpServer();
                }
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при проверке статуса HTTP сервера: {ex}");
            }
        }
        
        // Безопасный перезапуск HTTP сервера с освобождением ресурсов
        private void SafeRestartHttpServer()
        {
            try
            {
                if (listener != null)
                {
                    // Безопасно освобождаем ресурсы
                    try 
                    { 
                        if (listener.IsListening)
                            listener.Stop(); 
                    } 
                    catch { }
                    
                    try 
                    { 
                        listener.Close(); 
                    } 
                    catch { }
                    
                    listener = null; // Важно обнулить для сборщика мусора
                }
                
                // Проверяем, доступен ли порт перед перезапуском
                if (IsPortAvailable(8080))
                {
                    StartHttpServer();
                }
                else
                {
                    _logger.Error("Не удалось перезапустить HTTP сервер: порт 8080 уже занят");
                }
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при перезапуске HTTP сервера: {ex}");
            }
        }
        
        // Единый метод для проверки всех параметров
        private void CheckAllParameters(float dt)
        {
            try
            {
                // Увеличиваем счетчик для периодических обновлений
                _periodicUpdateCounter += dt;
                
                // 1. Проверка шторма
                CheckTemporalStormInternal();
                
                // 2. Проверка сезона
                CheckSeasonChangeInternal();
                
                // 3. Проверка количества игроков
                CheckPlayerCountInternal();
                
                // 4. Периодическая отправка статуса сервера (каждые 30 секунд)
                // ВАЖНО: Это значение должно соответствовать настройке CHANNEL_UPDATE в Discord-боте (0.5 минуты)
                if (_periodicUpdateCounter >= 30000)
                {
                    // Сбрасываем счетчик
                    _periodicUpdateCounter = 0;
                    
                    // Создаем объект уведомления с текущим статусом
                    var notification = new ServerStatusNotification
                    {
                        IsOnline = true, // Сервер всегда онлайн, если этот код выполняется
                        PlayerCount = _lastPlayerCount,
                        Message = $"Периодическое обновление статуса сервера",
                        Players = api.World.AllOnlinePlayers.Select(p => p.PlayerName).ToArray()
                    };
                    
                    // Отправляем уведомление в Discord
                    SendServerStatusNotification(notification);
                    
                    _logger?.Warning("Отправлено периодическое обновление статуса сервера");
                }
                
                // 5. Проверка статуса сервера
                CheckServerStatus(dt);
            }
            catch (Exception ex)
            {
                _logger?.Error($"Ошибка при выполнении единой проверки параметров: {ex}");
            }
        }
        
        // Внутренний метод для проверки шторма (без параметра dt)
        private void CheckTemporalStormInternal()
        {
            if (_disposed || api == null) return;
            
            try
            {
                var systems = api.ModLoader.GetModSystem<SystemTemporalStability>();
                if (systems?.StormData == null) return;
                
                bool currentStormStatus = systems.StormData.nowStormActive;
                
                // Предупреждение о приближающемся шторме (за 0.25 дней до начала)
                if (!currentStormStatus && !_stormWarningIssued && 
                    systems.StormData.nextStormTotalDays - api.World.Calendar.TotalDays < 0.25)
                {
                    _stormWarningIssued = true;
                    SendDiscordNotification(new StormForecast { 
                        IsActive = false, 
                        Message = "", 
                        IsWarning = true 
                    });
                    _logger.Warning("Отправлено предупреждение о шторме");
                }
                
                // Изменение статуса шторма
                if (currentStormStatus != _lastStormStatus)
                {
                    if (currentStormStatus)
                    {
                        // Шторм начался
                        SendDiscordNotification(new StormForecast { 
                            IsActive = true, 
                            Message = "", 
                            IsWarning = false 
                        });
                        _logger.Warning("Отправлено уведомление о начале шторма");
                    }
                    else
                    {
                        // Шторм закончился
                        _stormWarningIssued = false;
                        SendDiscordNotification(new StormForecast { 
                            IsActive = false, 
                            Message = "", 
                            IsWarning = false 
                        });
                        _logger.Warning("Отправлено уведомление об окончании шторма");
                    }
                    
                    _lastStormStatus = currentStormStatus;
                }
            }
            catch (Exception ex)
            {
                _logger?.Error($"Ошибка при проверке темпорального шторма: {ex}");
            }
        }
        
        // Внутренний метод для проверки сезона (без параметра dt)
        private void CheckSeasonChangeInternal()
        {
            if (_disposed || api == null) return;
            
            try
            {
                string currentSeason = GetCurrentSeason();
                
                if (!string.IsNullOrEmpty(currentSeason) && 
                    currentSeason != "Unknown" && 
                    !string.IsNullOrEmpty(_lastSeason) && 
                    _lastSeason != currentSeason)
                {
                    _logger.Warning($"Смена сезона: {_lastSeason} -> {currentSeason}");
                    
                    SendSeasonNotification(new SeasonNotification { 
                        Season = currentSeason, 
                        Message = "", 
                        IsNewSeason = true 
                    });
                }
                
                if (currentSeason != "Unknown" && _lastSeason != currentSeason)
                {
                    _lastSeason = currentSeason;
                }
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при проверке смены сезона: {ex}");
            }
        }
        
        // Внутренний метод для проверки количества игроков (без параметра dt)
        private void CheckPlayerCountInternal()
        {
            try
            {
                // Получаем текущее количество игроков
                int currentPlayerCount = api.World.AllOnlinePlayers.Length;
                bool isServerOnline = true; // Сервер всегда онлайн, если этот код выполняется
                
                // Если количество игроков изменилось или статус сервера изменился, отправляем уведомление
                if (currentPlayerCount != _lastPlayerCount || isServerOnline != _lastServerOnline)
                {
                    // Обновляем последние значения
                    _lastPlayerCount = currentPlayerCount;
                    _lastServerOnline = isServerOnline;
                    
                    // Создаем объект уведомления
                    var notification = new ServerStatusNotification
                    {
                        IsOnline = isServerOnline,
                        PlayerCount = currentPlayerCount,
                        Message = $"Игроков онлайн: {currentPlayerCount}",
                        Players = api.World.AllOnlinePlayers.Select(p => p.PlayerName).ToArray()
                    };
                    
                    // Отправляем уведомление в Discord
                    SendServerStatusNotification(notification);
                }
            }
            catch (Exception ex)
            {
                _logger?.Error($"Ошибка при проверке количества игроков: {ex}");
            }
        }
        
        // Метод для обработки и отправки накопленных уведомлений
        private void ProcessNotificationBuffer(float dt)
        {
            // Обновляем счетчик времени
            _notificationSendCounter += dt;
            
            // Проверяем, пора ли отправлять уведомления
            if (_notificationSendCounter < NotificationSendInterval)
            {
                return; // Ещё не время отправлять
            }
            
            // Сбрасываем счетчик
            _notificationSendCounter = 0;
            
            // Проверяем, есть ли уведомления для отправки
            List<NotificationItem> notifications;
            
            lock (_bufferLock)
            {
                if (_notificationBuffer.Count == 0)
                {
                    return; // Буфер пуст, нечего отправлять
                }
                
                // Копируем текущий буфер и очищаем его
                notifications = new List<NotificationItem>(_notificationBuffer);
                _notificationBuffer.Clear();
            }
            
            // Создаем пакет с уведомлениями
            var batchRequest = new
            {
                type = "notification_batch",
                timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"),
                notifications = notifications.Select(n => new
                {
                    type = n.Type,
                    data = n.Data,
                    timestamp = n.TimeAdded.ToString("yyyy-MM-dd HH:mm:ss")
                }).ToArray()
            };
            
            // Отправляем пакет уведомлений
            SendBatchNotification(batchRequest);
        }
        
        // Метод для отправки пакета уведомлений
        private void SendBatchNotification(object batchData)
        {
            try
            {
                string jsonString = JsonConvert.SerializeObject(batchData);
                var content = new StringContent(jsonString, Encoding.UTF8, "application/json");
                
                Task.Run(async () =>
                {
                    try
                    {
                        var response = await httpClient.PostAsync(DiscordBotUrl, content);
                        
                        if (!response.IsSuccessStatusCode)
                        {
                            var errorContent = await response.Content.ReadAsStringAsync();
                            _logger?.Warning($"Ошибка отправки пакета уведомлений. Код: {response.StatusCode}, Ответ: {errorContent}");
                        }
                    }
                    catch (Exception ex)
                    {
                        _logger.Error($"Ошибка при отправке пакета уведомлений: {ex.Message}");
                    }
                });
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при формировании пакета уведомлений: {ex.Message}");
            }
        }

        // Общий метод для добавления уведомлений в буфер
        private void SendHttpNotification(object data, string notificationType)
        {
            try
            {
                lock (_bufferLock)
                {
                    _notificationBuffer.Add(new NotificationItem(data, notificationType));
                }
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при добавлении уведомления о {notificationType} в буфер: {ex.Message}");
            }
        }

        private void SendDiscordNotification(StormForecast forecast)
        {
            try
            {
                // Получаем игровое время
                string gameTime = api?.World?.Calendar?.PrettyDate() ?? "Неизвестно";
                
                // Формируем JSON-запрос
                var requestData = new
                {
                    type = "storm_notification",
                    is_active = forecast.IsActive,
                    is_warning = forecast.IsWarning,
                    message = forecast.Message,
                    time = gameTime
                };
                
                // Отправляем уведомление
                SendHttpNotification(requestData, "шторме");
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при подготовке данных о шторме: {ex.Message}");
            }
        }
        
        private void SendSeasonNotification(SeasonNotification notification)
        {
            try
            {
                // Получаем игровое время
                string gameTime = api?.World?.Calendar?.PrettyDate() ?? "Неизвестно";
                
                // Формируем JSON-запрос
                var requestData = new
                {
                    type = "season_notification",
                    season = notification.Season.ToLowerInvariant(),
                    is_new_season = notification.IsNewSeason,
                    message = notification.Message,
                    time = gameTime
                };
                
                // Отправляем уведомление
                SendHttpNotification(requestData, "смене сезона");
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при подготовке данных о сезоне: {ex.Message}");
            }
        }
        
        // Метод для отправки уведомления о статусе сервера в Discord
        private void SendServerStatusNotification(ServerStatusNotification notification)
        {
            try
            {
                var requestData = new
                {
                    type = "server_status",
                    online = notification.IsOnline,
                    player_count = notification.PlayerCount,
                    players = notification.Players ?? new string[0],
                    message = notification.Message,
                    time = api?.World?.Calendar?.PrettyDate() ?? "Неизвестно"
                };
                
                // Отправляем уведомление
                SendHttpNotification(requestData, "статусе сервера");
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при подготовке данных о статусе сервера: {ex.Message}");
            }
        }

        // Метод для отправки начального уведомления о статусе сервера
        private void SendInitialServerStatus()
        {
            try
            {
                int currentPlayerCount = api.World.AllOnlinePlayers.Length;
                string[] playerNames = api.World.AllOnlinePlayers.Select(p => p.PlayerName).ToArray();
                
                var notification = new ServerStatusNotification
                {
                    IsOnline = true,
                    PlayerCount = currentPlayerCount,
                    Message = $"Сервер запущен, игроков онлайн: {currentPlayerCount}",
                    Players = playerNames
                };
                
                SendServerStatusNotification(notification);
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при отправке начального уведомления о статусе сервера: {ex}");
            }
        }
        
        // Обработчик события подключения игрока
        private void OnPlayerJoin(IServerPlayer player)
        {
            try
            {
                int currentPlayerCount = api.World.AllOnlinePlayers.Length;
                string[] playerNames = api.World.AllOnlinePlayers.Select(p => p.PlayerName).ToArray();
                
                _lastPlayerCount = currentPlayerCount;
                
                var notification = new ServerStatusNotification
                {
                    IsOnline = true,
                    PlayerCount = currentPlayerCount,
                    Message = "", // Пустое сообщение, чтобы не показывать уведомление в чате
                    Players = playerNames
                };
                
                SendServerStatusNotification(notification);
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при обработке подключения игрока: {ex}");
            }
        }
        
        // Обработчик события отключения игрока
        private void OnPlayerDisconnect(IServerPlayer player)
        {
            try
            {
                int currentPlayerCount = api.World.AllOnlinePlayers.Length;
                string[] playerNames = api.World.AllOnlinePlayers.Select(p => p.PlayerName).ToArray();
                
                _lastPlayerCount = currentPlayerCount;
                
                var notification = new ServerStatusNotification
                {
                    IsOnline = true,
                    PlayerCount = currentPlayerCount,
                    Message = "", // Пустое сообщение, чтобы не показывать уведомление в чате
                    Players = playerNames
                };
                
                SendServerStatusNotification(notification);
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при обработке отключения игрока: {ex}");
            }
        }
        
        // Метод для отправки периодических обновлений статуса сервера (каждые 20 секунд)
        private void SendPeriodicServerStatus(float dt)
        {
            try
            {
                int currentPlayerCount = api.World.AllOnlinePlayers.Length;
                string[] playerNames = api.World.AllOnlinePlayers.Select(p => p.PlayerName).ToArray();
                
                var notification = new ServerStatusNotification
                {
                    IsOnline = true,
                    PlayerCount = currentPlayerCount,
                    Message = "", // Пустое сообщение для heartbeat - не отображать в чате
                    Players = playerNames
                };
                
                string gameTime = api?.World?.Calendar?.PrettyDate() ?? "Неизвестно";
                
                var requestData = new
                {
                    type = "server_status",
                    online = true,
                    player_count = currentPlayerCount,
                    players = playerNames,
                    message = "", // Пустое сообщение - не отображать в чате
                    time = gameTime,
                    is_heartbeat = true // Флаг для бота, что это пульс сервера, не требующий уведомления
                };
                
                SendHttpNotification(requestData, "heartbeat");
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при отправке периодического обновления статуса сервера: {ex}");
            }
        }

        // Получение текущего сезона на основе игрового календаря
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
        
        // Определение сезона по месяцу
        private string GetSeasonByMonth(string month)
        {
            // Обрезаем окончания и запятые
            month = month.TrimEnd(',', '.').ToLowerInvariant();
            
            // Весна: март, апрель, май
            if (month.StartsWith("март") || month.StartsWith("апрел") || month.StartsWith("мая") || month == "май")
                return "весна";
            
            // Лето: июнь, июль, август
            if (month.StartsWith("июн") || month.StartsWith("июл") || month.StartsWith("август"))
                return "лето";
            
            // Осень: сентябрь, октябрь, ноябрь
            if (month.StartsWith("сентябр") || month.StartsWith("октябр") || month.StartsWith("ноябр"))
                return "осень";
            
            // Зима: декабрь, январь, февраль
            if (month.StartsWith("декабр") || month.StartsWith("январ") || month.StartsWith("феврал"))
                return "зима";
            
            _logger.Warning($"Не удалось определить сезон для месяца: '{month}'");
            return "Unknown";
        }
    }
}
