{-# LANGUAGE OverloadedStrings #-}

import Data.List (isPrefixOf)
import Data.Monoid ((<>))
import Hakyll
import System.FilePath (replaceExtension)
import System.Process (callProcess)

main :: IO ()
main = do
  callProcess "python3" ["scripts/build-films.py"]
  hakyll $ do
    match "css/*" $ do
        route idRoute
        compile compressCssCompiler

    match ("images/**" .||. "js/*") $ do
        route idRoute
        compile copyFileCompiler

    match "generated/**.md" $ do
        route $ customRoute $ \identifier ->
            replaceExtension (drop (length ("generated/" :: String)) (toFilePath identifier)) "html"
        compile $
            pandocCompiler
                >>= saveSnapshot "content"
                >>= loadAndApplyTemplate "templates/film-section.html" siteCtx
                >>= loadAndApplyTemplate "templates/default.html" siteCtx
                >>= relativizeUrls

    match "generated/home.html" $ compile getResourceBody

    match imagePattern $ do
        route idRoute
        compile copyFileCompiler

    match "posts/*/index.md" $ do
        route cleanPostRoute
        compile $
            pandocCompiler
                >>= saveSnapshot "content"
                >>= loadAndApplyTemplate "templates/post.html" postCtx
                >>= loadAndApplyTemplate "templates/default.html" siteCtx
                >>= relativizeUrls

    create ["index.html"] $ do
        route idRoute
        compile $ do
            posts <- fmap (take 3) . recentFirst =<< loadAllSnapshots "posts/*/index.md" "content"
            home <- loadBody "generated/home.html"

            let indexCtx =
                    listField "posts" postCtx (return posts)
                    <> constField "homeContent" home
                    <> boolField "hasPosts" (const $ not $ null posts)
                    <> constField "title" "Home"
                    <> siteCtx

            makeItem ""
                >>= loadAndApplyTemplate "templates/home.html" indexCtx
                >>= loadAndApplyTemplate "templates/default.html" indexCtx
                >>= relativizeUrls

    create ["archive.html"] $ do
        route idRoute
        compile $ do
            posts <- recentFirst =<< loadAllSnapshots writingPattern "content"

            let archiveCtx =
                    listField "posts" postCtx (return posts)
                    <> constField "title" "archive"
                    <> siteCtx

            makeItem ""
                >>= loadAndApplyTemplate "templates/archive.html" archiveCtx
                >>= loadAndApplyTemplate "templates/default.html" archiveCtx
                >>= relativizeUrls

    create ["rss.xml"] $ do
        route idRoute
        compile $ do
            posts <- fmap (take 20) . recentFirst =<< loadAllSnapshots writingPattern "content"
            let absolute url = if "/" `isPrefixOf` url && not ("//" `isPrefixOf` url) then "https://t0mb.net" ++ url else url
            renderRss feedConfig feedCtx (map (fmap $ withUrls absolute) posts)

    match "templates/*" $ compile templateBodyCompiler

    match "software.md" $ do
        route $ setExtension "html"
        compile $
            pandocCompiler
                >>= loadAndApplyTemplate "templates/default.html" siteCtx
                >>= relativizeUrls

writingPattern :: Pattern
writingPattern = "posts/*/index.md" .||. "generated/films/*/reviews/*/index.md"

imagePattern :: Pattern
imagePattern =
    "posts/**.jpg"
    .||. "posts/**.jpeg"
    .||. "posts/**.png"
    .||. "posts/**.gif"
    .||. "posts/**.webp"
    .||. "posts/**.avif"

cleanPostRoute :: Routes
cleanPostRoute =
    customRoute $ \identifier ->
        replaceExtension (toFilePath identifier) "html"

siteCtx :: Context String
siteCtx =
    constField "siteTitle" "t0mb.net"
    <> constField "siteDescription" "Brain spill"
    <> constField "builtWith" "Site built with <a href=https://jaspervdj.be/hakyll/>Hakyll</a>"
    <> defaultContext

postCtx :: Context String
postCtx =
    dateField "date" "%Y-%m-%d"
    <> defaultContext

feedCtx :: Context String
feedCtx =
    postCtx
    <> bodyField "description"

feedConfig :: FeedConfiguration
feedConfig = FeedConfiguration
    { feedTitle       = "t0mb.net"
    , feedDescription = "Brain spill"
    , feedAuthorName  = "Tom Boland"
    , feedAuthorEmail = ""
    , feedRoot        = "https://t0mb.net"
    }
