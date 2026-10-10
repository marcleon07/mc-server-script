package dev.mcserver.serverlink;

import org.bukkit.Bukkit;
import org.bukkit.ChatColor;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.command.ProxiedCommandSender;
import org.bukkit.configuration.ConfigurationSection;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.plugin.java.JavaPlugin;

import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Sends players to other servers behind the Velocity proxy (BungeeCord "Connect" plugin message).
 * Each entry under "links" in config.yml becomes a command. A link can also tell the target server
 * (running ServerLink with the same shared-folder) where to put the player and which command to run
 * for them on arrival, e.g. "/bw autojoin" in the lobby joins BedWars on the minigames server.
 * The optional "send-home" area sends players who stand in it back to another server.
 */
public final class ServerLink extends JavaPlugin implements Listener {
    private Path shared;
    private final Map<UUID, Long> joinedAt = new HashMap<>();
    private final Map<UUID, Long> leaving = new HashMap<>();

    @Override
    public void onEnable() {
        saveDefaultConfig();
        shared = Path.of(getConfig().getString("shared-folder", "../shared")).toAbsolutePath().normalize();
        try {
            Files.createDirectories(shared);
        } catch (IOException e) {
            getLogger().warning("Cannot create shared folder " + shared + ": " + e.getMessage());
        }
        getServer().getMessenger().registerOutgoingPluginChannel(this, "BungeeCord");
        getServer().getPluginManager().registerEvents(this, this);

        ConfigurationSection links = getConfig().getConfigurationSection("links");
        if (links != null) {
            for (String name : links.getKeys(false)) registerLink(name, links.getConfigurationSection(name));
            getLogger().info("Links: " + links.getKeys(false) + ", shared folder " + shared);
        }
        if (getConfig().getBoolean("send-home.enabled", false)) startSendHome(getConfig().getConfigurationSection("send-home"));
    }

    private void registerLink(String name, ConfigurationSection link) {
        if (link == null || link.getString("server") == null) return;
        String server = link.getString("server");
        String world = link.getString("world", "");
        String location = link.getString("location", "");
        String template = link.getString("command", "");
        String defaultArgs = link.getString("default-args", "");
        List<String> aliases = link.getStringList("aliases");
        Command cmd = new Command(name, "Go to " + server, "/" + name, aliases) {
            @Override
            public boolean execute(CommandSender sender, String label, String[] args) {
                // "execute as <player> run ..." and command blocks arrive as a proxied sender
                CommandSender target = sender instanceof ProxiedCommandSender proxied ? proxied.getCallee() : sender;
                if (!(target instanceof Player player)) {
                    sender.sendMessage("Players only.");
                    return true;
                }
                String argLine = args.length > 0 ? String.join(" ", args) : defaultArgs;
                // "/bw" alone just travels; "/bw autojoin" also runs "bw autojoin" on arrival
                String command = template.contains("{args}") && argLine.isEmpty() ? "" : template.replace("{args}", argLine).trim();
                send(player, server, world, location, command);
                return true;
            }
        };
        Bukkit.getCommandMap().register("serverlink", cmd);
    }

    private void send(Player player, String server, String world, String location, String command) {
        if (!world.isEmpty() || !location.isEmpty() || !command.isEmpty()) {
            String data = "world=" + world + "\nlocation=" + location + "\ncommand=" + command + "\ntime=" + System.currentTimeMillis() + "\n";
            try {
                Files.writeString(pending(player.getUniqueId()), data, StandardCharsets.UTF_8);
            } catch (IOException e) {
                getLogger().warning("Cannot write pending destination: " + e.getMessage());
            }
        }
        connect(player, server);
    }

    private void connect(Player player, String server) {
        player.sendMessage(ChatColor.GRAY + "Sending you to " + ChatColor.GOLD + server + ChatColor.GRAY + "...");
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream(); DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeUTF("Connect");
            out.writeUTF(server);
            player.sendPluginMessage(this, "BungeeCord", bytes.toByteArray());
        } catch (IOException e) {
            player.sendMessage(ChatColor.RED + "Could not reach " + server + ".");
        }
    }

    private Path pending(UUID id) {
        return shared.resolve(id + ".txt");
    }

    @EventHandler
    public void onJoin(PlayerJoinEvent event) {
        Player player = event.getPlayer();
        joinedAt.put(player.getUniqueId(), System.currentTimeMillis());
        leaving.remove(player.getUniqueId());
        Path file = pending(player.getUniqueId());
        if (!Files.exists(file)) return;
        Map<String, String> data = new HashMap<>();
        try {
            for (String line : Files.readAllLines(file, StandardCharsets.UTF_8)) {
                int eq = line.indexOf('=');
                if (eq > 0) data.put(line.substring(0, eq).trim(), line.substring(eq + 1).trim());
            }
            Files.deleteIfExists(file);
        } catch (IOException e) {
            return;
        }
        long time;
        try {
            time = Long.parseLong(data.getOrDefault("time", "0"));
        } catch (NumberFormatException e) {
            return;
        }
        if (System.currentTimeMillis() - time > 120_000) return;
        String world = data.getOrDefault("world", "");
        String location = data.getOrDefault("location", "");
        String command = data.getOrDefault("command", "");
        // Let other join handlers (Multiverse, Essentials, minigames) finish first.
        Bukkit.getScheduler().runTaskLater(this, () -> {
            if (!player.isOnline()) return;
            Location target = parseLocation(location);
            if (target != null) {
                player.teleport(target);
            } else if (!world.isEmpty() && Bukkit.getWorld(world) != null) {
                Bukkit.dispatchCommand(Bukkit.getConsoleSender(), "mvtp " + player.getName() + " " + world);
            }
            if (!command.isEmpty()) {
                Bukkit.getScheduler().runTaskLater(this, () -> {
                    if (player.isOnline()) player.performCommand(command);
                }, 5L);
            }
        }, 10L);
    }

    @EventHandler
    public void onQuit(PlayerQuitEvent event) {
        joinedAt.remove(event.getPlayer().getUniqueId());
        leaving.remove(event.getPlayer().getUniqueId());
    }

    /** "world x y z [yaw pitch]" */
    private static Location parseLocation(String s) {
        if (s == null || s.isBlank()) return null;
        String[] p = s.trim().split("\\s+");
        if (p.length < 4) return null;
        World w = Bukkit.getWorld(p[0]);
        if (w == null) return null;
        try {
            float yaw = p.length > 4 ? Float.parseFloat(p[4]) : 0f;
            float pitch = p.length > 5 ? Float.parseFloat(p[5]) : 0f;
            return new Location(w, Double.parseDouble(p[1]), Double.parseDouble(p[2]), Double.parseDouble(p[3]), yaw, pitch);
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private void startSendHome(ConfigurationSection home) {
        String server = home.getString("server", "lobby");
        Location centre = parseLocation(home.getString("location", ""));
        double radius = home.getDouble("radius", 6);
        long grace = (long) (home.getDouble("grace-seconds", 5) * 1000);
        if (centre == null) {
            getLogger().warning("send-home.location is not a valid 'world x y z' in a loaded world");
            return;
        }
        double r2 = radius * radius;
        Bukkit.getScheduler().runTaskTimer(this, () -> {
            long now = System.currentTimeMillis();
            for (Player player : Bukkit.getOnlinePlayers()) {
                UUID id = player.getUniqueId();
                // retry every 10 s in case the target server is down
                if (now - leaving.getOrDefault(id, 0L) < 10_000 || now - joinedAt.getOrDefault(id, 0L) < grace) continue;
                Location at = player.getLocation();
                if (at.getWorld() != centre.getWorld() || at.distanceSquared(centre) > r2) continue;
                leaving.put(id, now);
                connect(player, server);
            }
        }, 20L, 10L);
        getLogger().info("Players within " + radius + " blocks of " + home.getString("location") + " are sent to " + server);
    }
}
